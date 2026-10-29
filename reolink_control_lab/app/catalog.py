"""Explicit, capability-gated camera controls. No arbitrary protocol commands."""
from dataclasses import dataclass, field, asdict
from typing import Any
from reolink_aio.enums import AntiFlickerEnum, ChimeToneEnum


def method(host, path):
    target = host
    for part in path.split('.'):
        target = getattr(target, part)
    return target


@dataclass
class Feature:
    key: str
    name: str
    kind: str
    capability: str = ''
    getter: str = ''
    getter_extra: tuple = ()
    setter: str = ''
    argument: str = 'value'
    extra: dict = field(default_factory=dict)
    options: list = field(default_factory=list)
    minimum: int = 0
    maximum: int = 100
    risky: bool = False
    unit: str | None = None
    device_class: str | None = None
    host_level: bool = False
    chime_id: int | None = None

    def available(self, host, channel, allow_risky):
        return (not self.risky or allow_risky) and (
            not self.capability or host.supported(None if self.host_level else channel, self.capability))

    def read(self, host, channel):
        if not self.getter:
            return None
        if self.chime_id is not None:
            target = host.chime(self.chime_id)
            value = getattr(target, self.getter)
            if callable(value):
                value = value(*self.getter_extra)
        else:
            value = method(host, self.getter)(channel, *self.getter_extra)
        if self.kind == 'select':
            if self.argument in ('file_id', 'tone_id'):
                return next((x for x in self.options if x.split(':', 1)[0] == str(value)), None)
            if self.key == 'doorbell_led':
                value = {'Off': 'stayoff', 'Auto': 'auto', 'AlwaysOnAtNight': 'alwaysonatnight'}.get(value, value)
            return str(value) if value is not None else None
        return value

    def validate(self, value):
        if self.kind == 'switch':
            if value is True or value == 'ON':
                return True
            if value is False or value == 'OFF':
                return False
            raise ValueError('Expected ON/OFF or a JSON boolean')
        if self.kind == 'number':
            if isinstance(value, bool):
                raise ValueError('A boolean is not a number')
            try:
                num = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError('Expected an integer') from exc
            if not num.is_integer() or not self.minimum <= num <= self.maximum:
                raise ValueError(f'Expected an integer between {self.minimum} and {self.maximum}')
            return int(num)
        if self.kind == 'select':
            if str(value) not in [str(x) for x in self.options]:
                raise ValueError('Value is not one of the advertised options')
            return value
        if self.kind == 'button':
            if value not in (None, 'PRESS'):
                raise ValueError('Expected PRESS')
            return None
        raise ValueError('This entity is read-only')

    async def write(self, host, channel, value):
        value = self.validate(value)
        if not self.setter:
            raise ValueError('This entity is read-only')
        kwargs = dict(self.extra)
        if self.argument in ('file_id', 'tone_id') and value is not None:
            value = int(str(value).split(':', 1)[0])
        if self.setter in ('set_frame_rate', 'set_bit_rate'):
            value = int(value)
        if not self.host_level and self.chime_id is None:
            kwargs['channel'] = channel
        if self.kind != 'button':
            kwargs[self.argument] = value
        target = getattr(host.chime(self.chime_id), self.setter) if self.chime_id is not None else method(host, self.setter)
        return await target(**kwargs)

    def public(self):
        return {k: v for k, v in asdict(self).items() if k not in ('getter', 'getter_extra', 'setter', 'argument', 'extra')}


def build_catalog(host, channel, allow_risky=False, events_enabled=False):
    items = []

    def add(key, name, kind, cap='', getter='', setter='', argument='value', **kwargs):
        f = Feature(key, name, kind, cap, getter, setter=setter, argument=argument, **kwargs)
        if f.available(host, channel, allow_risky):
            items.append(f)

    add('battery', 'Battery', 'sensor', 'battery', 'battery_percentage', unit='%', device_class='battery')
    add('temperature', 'Battery temperature', 'sensor', 'battery', 'battery_temperature', unit='°C', device_class='temperature')
    add('sleeping', 'Sleeping', 'binary_sensor', 'sleep', 'sleeping')
    add('wifi_signal', 'Wi-Fi signal', 'sensor', 'wifi', 'wifi_signal', host_level=True)
    for key, name in [('volume', 'Volume'), ('volume_speak', 'Speaker volume'), ('volume_doorbell', 'Doorbell volume')]:
        add(key, name, 'number', key, key, 'set_volume', key)
    add('button_sound', 'Doorbell button sound', 'switch', 'doorbell_button_sound', 'doorbell_button_sound', 'set_volume', 'doorbell_button_sound')
    add('record_audio', 'Record audio', 'switch', 'audio', 'audio_record', 'set_audio', 'enable')
    add('ir', 'Infrared lights', 'switch', 'ir_lights', 'ir_enabled', 'set_ir_lights', 'enable')
    add('status_led', 'Status LED', 'switch', 'status_led', 'status_led_enabled', 'set_status_led', 'state')
    modes = host.doorbell_led_list(channel)
    if modes:
        add('doorbell_led', 'Doorbell LED', 'select', 'doorbell_led', 'doorbell_led', 'set_status_led', 'state', options=modes, extra={'doorbell': True})
    add('daynight', 'Day/night mode', 'select', 'dayNight', 'daynight_state', 'set_daynight', options=['Auto', 'Color', 'Black&White'])
    add('anti_flicker', 'Anti-flicker', 'select', 'anti_flicker', 'anti_flicker_mode', 'set_anti_flicker', options=[x.value for x in AntiFlickerEnum])
    for key, arg in [('brightness', 'bright'), ('contrast', 'contrast'), ('saturation', 'saturation'), ('sharpness', 'sharpen')]:
        cap = {'brightness': 'isp_bright', 'contrast': 'isp_contrast', 'saturation': 'isp_satruation', 'sharpness': 'isp_sharpen'}[key]
        add(key, key.title(), 'number', cap, 'image_' + key, 'set_image', arg, minimum=0, maximum=255)
    add('pir_sensitivity', 'PIR sensitivity', 'number', 'PIR_sensitivity', 'pir_sensitivity', 'set_pir', 'sensitivity', minimum=1)
    add('motion_sensitivity', 'Motion sensitivity', 'number', 'motion_detection', 'md_sensitivity', 'set_md_sensitivity', minimum=1, maximum=50)
    for ai_type in host.ai_supported_types(channel):
        add('ai_' + ai_type, ai_type.replace('_', ' ').title() + ' detected', 'binary_sensor', 'ai_' + ai_type,
            'ai_detected', getter_extra=(ai_type,))
        add('ai_sensitivity_' + ai_type, ai_type.replace('_', ' ').title() + ' sensitivity', 'number', 'ai_sensitivity',
            'ai_sensitivity', 'set_ai_sensitivity', getter_extra=(ai_type,), extra={'ai_type': ai_type})
        add('ai_delay_' + ai_type, ai_type.replace('_', ' ').title() + ' detection delay', 'number', 'ai_sensitivity',
            'ai_delay', 'set_ai_delay', getter_extra=(ai_type,), extra={'ai_type': ai_type}, maximum=8, unit='s')
    for stream in ('main', 'sub'):
        for name, cap, getter, setter in [('bit_rate', 'bit_rate', 'bit_rate', 'set_bit_rate'), ('frame_rate', 'frame_rate', 'frame_rate', 'set_frame_rate')]:
            values = getattr(host, getter + '_list')(channel, stream)
            if values:
                add(stream + '_' + name, stream.title() + ' ' + name.replace('_', ' '), 'select', cap,
                    getter, setter, getter_extra=(stream,), options=[str(x) for x in values], extra={'stream': stream})
    for cap, getter, setter in [('work_mode_battery', 'work_mode_battery', 'baichuan.set_work_mode_battery'),
                                ('work_mode_powered', 'work_mode_powered', 'baichuan.set_work_mode_powered')]:
        modes = getattr(host, getter + '_list')(channel)
        if modes:
            add(cap, cap.replace('_', ' ').title(), 'select', cap, getter, setter, 'mode', options=modes, risky=True)
    replies = host.quick_reply_dict(channel)
    reply_options = [str(k) + ': ' + v for k, v in replies.items() if k >= 0]
    if reply_options:
        add('play_reply', 'Play quick reply', 'select', 'play_quick_reply', setter='play_quick_reply', argument='file_id', options=reply_options, risky=True)
        add('auto_reply_file', 'Automatic quick reply', 'select', 'quick_reply', 'quick_reply_file', 'set_quick_reply', 'file_id', options=reply_options)
    add('auto_reply', 'Automatic reply enabled', 'switch', 'quick_reply', 'quick_reply_enabled', 'set_quick_reply', 'enable')
    add('reply_delay', 'Automatic reply delay', 'number', 'quick_reply', 'quick_reply_time', 'set_quick_reply', 'time', maximum=60, unit='s')
    add('post_record', 'Post-recording time', 'select', 'post_rec_time', 'post_recording_time', 'set_post_recording_time', options=host.post_recording_time_list(channel))
    # Potentially disruptive operations require an explicit add-on option.
    for key, name, cap, getter, setter in [
        ('recording', 'Recording enabled', 'rec_enable', 'recording_enabled', 'set_recording'),
        ('pir', 'PIR detection enabled', 'PIR_sensitivity', 'pir_enabled', 'set_pir'),
        ('privacy', 'Privacy mode', 'privacy_mode', 'baichuan.privacy_mode', 'baichuan.set_privacy_mode'),
        ('privacy_mask', 'Privacy masks enabled', 'privacy_mask_basic', 'privacy_mask_enabled', 'set_privacy_mask'),
        ('push', 'Push notifications', 'push', 'push_enabled', 'set_push'),
        ('email', 'Email notifications', 'email', 'email_enabled', 'set_email'),
        ('ftp', 'FTP upload', 'ftp', 'ftp_enabled', 'set_ftp'),
        ('siren_on_event', 'Siren on event', 'siren', 'audio_alarm_enabled', 'set_audio_alarm'),
    ]:
        add(key, name, 'switch', cap, getter, setter, 'enable', risky=True)
    add('siren_short', 'Siren two pulses', 'button', 'siren_play', setter='set_siren', extra={'enable': True, 'duration': 2}, risky=True)
    add('siren_stop', 'Stop siren', 'button', 'siren_play', setter='set_siren', extra={'enable': False}, risky=True)
    add('reboot', 'Restart camera', 'button', 'reboot', setter='baichuan.reboot', risky=True, host_level=True)
    add('sync_time', 'Synchronize camera time', 'button', 'sync_time', setter='baichuan.synchronize_time', host_level=True)
    add('motion', 'Motion detected', 'binary_sensor', 'motion_detection', 'motion_detected')
    if events_enabled:
        add('visitor', 'Doorbell pressed', 'binary_sensor', getter='visitor_detected')
    if allow_risky:
        add('hardwired_chime', 'Hardwired chime enabled', 'switch', 'hardwired_chime', 'baichuan.hardwired_chime_enabled',
            'baichuan.set_ding_dong_ctrl', 'enable', risky=True)
    for chime in host.chime_list:
        prefix = 'chime_' + str(chime.dev_id) + '_'
        for key, name, kind, getter, setter, arg, maximum in [
            ('volume', 'volume', 'number', 'volume', 'set_option', 'volume', 4),
            ('led', 'LED', 'switch', 'led_state', 'set_option', 'led', 1),
            ('silent_time', 'silent time', 'number', 'silent_time', 'set_silent_time', 'time', 43200),
        ]:
            if getter == 'silent_time' and not allow_risky:
                continue
            add(prefix + key, chime.name + ' ' + name, kind, getter=getter, setter=setter, argument=arg,
                chime_id=chime.dev_id, maximum=maximum, risky=getter == 'silent_time')
        tones = [str(x.value) + ': ' + x.name for x in ChimeToneEnum]
        if allow_risky:
            add(prefix + 'play', chime.name + ' play tone', 'select', setter='play', argument='tone_id',
                chime_id=chime.dev_id, options=[x for x in tones if not x.startswith('-1:')], risky=True)
        for event_type in chime.chime_event_types:
            add(prefix + 'tone_' + event_type, chime.name + ' ' + event_type + ' tone', 'select',
                getter='tone', setter='set_tone', argument='tone_id', chime_id=chime.dev_id,
                getter_extra=(event_type,), extra={'event_type': event_type}, options=tones)
    return [f for f in items if f.kind != 'select' or f.options]
