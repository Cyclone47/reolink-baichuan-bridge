"""Camera sessions, cached state, MQTT discovery and opt-in webhook ownership."""
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import ssl
from xml.etree import ElementTree as ET

import aiomqtt
from reolink_aio.api import Host
from reolink_aio.enums import ConnectionEnum

from catalog import build_catalog

LOG = logging.getLogger('control_lab')


class ControlService:
    def __init__(self, options, data_dir='/data', host=None):
        self.options = options
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.channel = options.get('camera_channel', 0)
        self.host = host or Host(options['camera_address'], options['camera_username'], options['camera_password'],
                                 bc_only=True, bc_connection=ConnectionEnum.udp, uid=options.get('camera_uid') or 'Unknown')
        self.identity = hashlib.sha256((options['camera_address'] + ':' + str(self.channel)).encode()).hexdigest()[:12]
        self.base = 'reolink_control_lab/' + self.identity
        self.features = {}
        self.values = {}
        self.errors = {}
        self.connected = False
        self.updated = None
        self.lock = asyncio.Lock()
        self.client = None
        self.tasks = []
        self.closed = False
        self.webhook_url = None
        self.webhook_original = None
        self.webhook_path = '/webhook/' + secrets.token_urlsafe(24)
        self.csrf = secrets.token_urlsafe(24)
        self.events_active = False
        self.event_tasks = {}
        self.last_events = {}
        self.snapshot = None
        self.mqtt_error = None
        self.on_change = None

    def redact(self, exc):
        text = str(exc)
        for key in ('camera_password', 'camera_uid', 'mqtt_password'):
            value = self.options.get(key)
            if value:
                text = text.replace(value, '[REDACTED]')
        if self.webhook_url:
            text = text.replace(self.webhook_url, '[EVENT_ENDPOINT]')
        return text[:350]

    def metadata(self):
        return {'connected': self.connected, 'updated': self.updated,
                'mqtt_connected': self.client is not None, 'mqtt_error': self.mqtt_error,
                'events_active': self.events_active,
                'features': [f.public() for f in self.features.values()],
                'values': self.values, 'errors': self.errors, 'last_events': self.last_events,
                'read_only': self.options.get('read_only', True),
                'disruptive_enabled': self.options.get('allow_disruptive_actions', False),
                'advertised': self.advertised(),
                'limitations': ['Advertised capabilities do not prove a setter works on beta firmware.',
                                'Two-way audio transport, custom TTS/upload, firmware flashing and network/account changes are not implemented.']}

    def advertised(self):
        result = set()
        for groups in getattr(self.host, '_capabilities', {}).values():
            for caps in groups.values():
                result.update(caps)
        return sorted(result)

    async def start(self):
        # This read-only discovery is the only automatic camera access by default.
        try:
            await self.refresh(initial=True)
        except Exception as exc:
            self.errors['connection'] = self.redact(exc)
            LOG.warning('Initial camera read failed: %s', type(exc).__name__)
        if self.options.get('mqtt_host'):
            self.tasks.append(asyncio.create_task(self.mqtt_loop()))
        interval = self.options.get('poll_interval', 0)
        if interval:
            self.tasks.append(asyncio.create_task(self.poll_loop(interval)))

    async def refresh(self, initial=False):
        async with self.lock:
            try:
                if initial or not self.features:
                    await asyncio.wait_for(self.host.get_host_data(), 45)
                else:
                    await asyncio.wait_for(self.host.get_states(wake=True), 45)
                reads = []
                if self.host.supported(self.channel, 'PIR_sensitivity'):
                    reads.append(('pir', lambda: self.host.baichuan.GetPirInfo(self.channel)))
                if self.host.supported(self.channel, 'ai_sensitivity'):
                    reads.append(('ai_settings', lambda: self.host.baichuan.GetAllAiAlarm(self.channel)))
                if self.host.supported(None, 'wifi'):
                    reads.append(('wifi', lambda: self.host.baichuan.get_wifi_signal()))
                for chime in self.host.chime_list:
                    reads.append(('chime_' + str(chime.dev_id), lambda chime=chime:
                                  self.host.baichuan.get_DingDongOpt(channel=chime.channel, chime_id=chime.dev_id)))
                for label, read in reads:
                    try:
                        await asyncio.wait_for(read(), 8)
                        self.errors.pop('read_' + label, None)
                    except Exception as exc:
                        self.errors['read_' + label] = self.redact(exc)
                if self.host.supported(self.channel, 'quick_reply'):
                    for call in (self.host.baichuan.GetAudioFileList, self.host.baichuan.GetAutoReply):
                        try:
                            await asyncio.wait_for(call(self.channel), 8)
                        except Exception as exc:
                            self.errors['quick_reply'] = self.redact(exc)
                features = build_catalog(self.host, self.channel, self.options.get('allow_disruptive_actions', False), self.events_active)
                self.features = {f.key: f for f in features}
                self.connected = True
                self.errors.pop('connection', None)
                self.updated = datetime.now(timezone.utc).isoformat()
                self.collect()
            except Exception as exc:
                self.connected = False
                self.errors['connection'] = self.redact(exc)
                await self.publish_all()
                raise
        await self.publish_all()
        return self.metadata()

    def collect(self):
        for key, f in self.features.items():
            try:
                value = f.read(self.host, self.channel)
                # Avoid library fallback values masquerading as measured telemetry.
                if key in ('battery', 'temperature') and self.channel not in getattr(self.host, '_battery', {}):
                    value = None
                if key == 'pir_sensitivity' and 'read_pir' in self.errors:
                    value = None
                if key.startswith(('ai_sensitivity_', 'ai_delay_')) and 'read_ai_settings' in self.errors:
                    value = None
                if key in ('motion', 'visitor') or key.startswith('ai_') and f.kind == 'binary_sensor':
                    value = self.values.get(key, False) if self.events_active else None
                self.values[key] = value
                self.errors.pop(key, None)
            except Exception as exc:
                self.values[key] = None
                self.errors[key] = self.redact(exc)

    async def command(self, key, value):
        if self.options.get('read_only', True):
            raise ValueError('Read-only mode is enabled. Turn it off in the app configuration before changing settings.')
        if key not in self.features:
            raise ValueError('Unknown, unsupported or disabled action')
        f = self.features[key]
        if not f.setter:
            raise ValueError('This entity is read-only')
        f.validate(value)
        async with self.lock:
            try:
                await asyncio.wait_for(f.write(self.host, self.channel, value), 25)
                self.errors.pop(key, None)
                self.collect()
                self.updated = datetime.now(timezone.utc).isoformat()
            except Exception as exc:
                self.errors[key] = self.redact(exc)
                raise
        # Publish cached read-back, never assume a successful write means it took effect.
        await self.publish_all()
        return self.metadata()

    async def take_snapshot(self):
        async with self.lock:
            image = await asyncio.wait_for(self.host.get_snapshot(self.channel), 25)
            if not image or not image.startswith(b'\xff\xd8'):
                raise ValueError('Camera did not return a JPEG snapshot')
            self.snapshot = image
        if self.client:
            await self.client.publish(self.base + '/snapshot', image, qos=1, retain=False)
        return image

    async def recordings(self, hours=24):
        if not isinstance(hours, int) or isinstance(hours, bool) or not 1 <= hours <= 24:
            raise ValueError('Recording searches are limited to 1–24 hours')
        end = datetime.now(timezone.utc)
        async with self.lock:
            _, files = await asyncio.wait_for(self.host.request_vod_files(self.channel, end - timedelta(hours=hours), end), 35)
        # Only safe, useful metadata; no playback URLs with credentials or device UID.
        return [{'start': str(getattr(f, 'start_time', '')), 'end': str(getattr(f, 'end_time', '')),
                 'size': getattr(f, 'size', None)} for f in files[:200]]

    async def setup_events(self, port):
        if not self.options.get('enable_events', False):
            return
        if self.options.get('read_only', True):
            self.errors['events'] = 'Disable read-only mode before explicitly enabling webhook registration.'
            return
        if not self.host.supported(None, 'bc_webhook'):
            self.errors['events'] = 'This firmware does not advertise battery webhooks.'
            return
        async with self.lock:
            original = ET.fromstring(await self.host.baichuan.send(cmd_id=806))
            old_url = original.findtext('.//url', '')
            old_enabled = original.findtext('.//enable', '0')
            backup_path = self.data_dir / 'webhook-backup.json'
            backup = json.loads(backup_path.read_text()) if backup_path.exists() else {}
            owned = backup.get('identity') == self.identity and backup.get('owned_url') == old_url
            if old_url and old_enabled == '1' and not owned and not self.options.get('replace_existing_webhook', False):
                self.errors['events'] = 'A webhook is already registered. Leave it in place or explicitly allow replacement in Configuration.'
                return
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((self.options['camera_address'], 2015))
                local_ip = sock.getsockname()[0]
            self.webhook_url = f'http://{local_ip}:{port}{self.webhook_path}'
            self.webhook_original = backup['original'] if owned else ET.tostring(original, encoding='unicode')
            backup_path.write_text(json.dumps({'identity': self.identity, 'owned_url': self.webhook_url,
                                               'original': self.webhook_original}))
            os.chmod(backup_path, 0o600)
            await self.host.baichuan.subscribe_events(self.webhook_url)
            self.events_active = self.host.baichuan.webhook_subscribed
            self.host.baichuan.register_callback('control-lab', self.on_event, cmd_id=33, channel=self.channel)
        await self.refresh()

    def on_event(self):
        if self.closed:
            return
        for key, f in self.features.items():
            if f.kind == 'binary_sensor' and key != 'sleeping':
                try:
                    self.values[key] = bool(f.read(self.host, self.channel))
                except Exception:
                    continue
            if f.kind == 'binary_sensor' and key != 'sleeping' and self.values.get(key):
                self.last_events[key] = datetime.now(timezone.utc).isoformat()
                if key in self.event_tasks:
                    self.event_tasks[key].cancel()
                self.event_tasks[key] = asyncio.create_task(self.reset_event(key))
        task = asyncio.create_task(self.publish_state())
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    async def reset_event(self, key):
        # These are event pulses, not a claim of sustained presence.
        await asyncio.sleep(5)
        self.values[key] = False
        await self.publish_state()

    def discovery(self):
        device = {'identifiers': ['reolink_control_lab_' + self.identity],
                  'name': self.options.get('camera_name', 'Doorbell') + ' Control Lab',
                  'manufacturer': 'Reolink', 'model': 'Local Baichuan device'}
        messages = {}
        for key, f in self.features.items():
            config = {'name': f.name, 'unique_id': self.identity + '_' + key, 'device': device,
                      'availability_topic': self.base + '/availability',
                      'origin': {'name': 'Reolink Control Lab', 'sw_version': '0.1.0'}}
            if f.kind != 'button':
                config.update(state_topic=self.base + '/state', value_template='{{ value_json.' + key + ' }}')
                if f.kind in ('switch', 'binary_sensor'):
                    config.update(payload_on='ON', payload_off='OFF', value_template=
                                  "{{ 'ON' if value_json." + key + " == true else 'OFF' if value_json." + key + " == false else 'None' }}")
                if f.unit:
                    config['unit_of_measurement'] = f.unit
                if f.device_class:
                    config['device_class'] = f.device_class
            if f.setter and not self.options.get('read_only', True):
                config['command_topic'] = self.base + '/set/' + key
                if f.kind == 'number':
                    config.update(min=f.minimum, max=f.maximum, step=1, mode='box')
                if f.kind == 'select':
                    config['options'] = f.options
            elif f.kind not in ('sensor', 'binary_sensor'):
                # In read-only mode expose ordinary values as sensors, not unusable actuators.
                config.pop('payload_on', None)
                config.pop('payload_off', None)
            kind = f.kind if f.setter and not self.options.get('read_only', True) or f.kind == 'binary_sensor' else 'sensor'
            if f.kind == 'button' and self.options.get('read_only', True):
                continue
            messages[f'homeassistant/{kind}/{self.identity}/{key}/config'] = config
        if self.host.supported(self.channel, 'snapshot'):
            messages[f'homeassistant/camera/{self.identity}/snapshot/config'] = {
                'name': 'Snapshot (manual)', 'unique_id': self.identity + '_snapshot', 'device': device,
                'topic': self.base + '/snapshot', 'availability_topic': self.base + '/availability'}
        messages[f'homeassistant/button/{self.identity}/refresh/config'] = {
            'name': 'Refresh camera', 'unique_id': self.identity + '_refresh', 'device': device,
            'command_topic': self.base + '/refresh', 'availability_topic': self.base + '/availability'}
        if self.host.supported(self.channel, 'snapshot'):
            messages[f'homeassistant/button/{self.identity}/take_snapshot/config'] = {
                'name': 'Take snapshot', 'unique_id': self.identity + '_take_snapshot', 'device': device,
                'command_topic': self.base + '/take_snapshot', 'availability_topic': self.base + '/availability'}
        return messages

    async def publish_state(self):
        if self.client:
            await self.client.publish(self.base + '/state', json.dumps(self.values), qos=1, retain=True)

    async def publish_all(self):
        if not self.client:
            return
        messages = self.discovery()
        ledger = self.data_dir / 'discovery.json'
        old_topics = set(json.loads(ledger.read_text())) if ledger.exists() else set()
        for topic in old_topics - set(messages):
            await self.client.publish(topic, b'', qos=1, retain=True)
        for topic, config in messages.items():
            await self.client.publish(topic, json.dumps(config), qos=1, retain=True)
        ledger.write_text(json.dumps(sorted(messages)))
        await self.client.publish(self.base + '/availability', 'online' if self.connected else 'offline', qos=1, retain=True)
        await self.publish_state()

    async def mqtt_loop(self):
        while not self.closed:
            try:
                tls = ssl.create_default_context() if self.options.get('mqtt_tls', False) else None
                async with aiomqtt.Client(hostname=self.options['mqtt_host'], port=self.options.get('mqtt_port', 1883),
                        username=self.options.get('mqtt_username') or None, password=self.options.get('mqtt_password') or None,
                        identifier='reolink_lab_' + self.identity, tls_context=tls,
                        will=aiomqtt.Will(self.base + '/availability', 'offline', qos=1, retain=True)) as client:
                    self.client = client
                    self.mqtt_error = None
                    await client.subscribe(self.base + '/set/+')
                    await client.subscribe(self.base + '/refresh')
                    await client.subscribe(self.base + '/take_snapshot')
                    await client.subscribe('homeassistant/status')
                    await self.publish_all()
                    async for message in client.messages:
                        if message.retain:
                            continue  # Never replay a retained command after reboot.
                        topic = str(message.topic)
                        payload = bytes(message.payload).decode()
                        try:
                            if topic == 'homeassistant/status':
                                if payload == 'online':
                                    await self.publish_all()
                            elif topic.endswith('/refresh') and payload == 'PRESS':
                                await self.refresh()
                            elif topic.endswith('/take_snapshot') and payload == 'PRESS':
                                await self.take_snapshot()
                            elif '/set/' in topic:
                                try:
                                    value = json.loads(payload)
                                except ValueError:
                                    value = payload
                                await self.command(topic.rsplit('/', 1)[1], value)
                        except Exception as exc:
                            await client.publish(self.base + '/result', json.dumps({'ok': False, 'error': self.redact(exc)}), retain=False)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.mqtt_error = self.redact(exc)
                LOG.warning('MQTT unavailable: %s', type(exc).__name__)
            finally:
                self.client = None
            await asyncio.sleep(10)

    async def poll_loop(self, interval):
        while True:
            await asyncio.sleep(interval)
            try:
                await self.refresh()
            except Exception:
                await self.publish_all()

    async def close(self):
        if self.closed:
            return
        self.closed = True
        if self.client:
            try:
                await self.client.publish(self.base + '/availability', 'offline', qos=1, retain=True)
            except Exception:
                pass
        for task in self.tasks + list(self.event_tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks, *self.event_tasks.values(), return_exceptions=True)
        if self.webhook_url and self.webhook_original:
            try:
                current = ET.fromstring(await self.host.baichuan.send(cmd_id=806))
                if current.findtext('.//url') == self.webhook_url:
                    root = ET.fromstring(self.webhook_original)
                    await self.host.baichuan.send(cmd_id=807, body=root)
            except Exception as exc:
                LOG.warning('Could not restore previous webhook: %s', type(exc).__name__)
        self.host.baichuan.unregister_callback('control-lab')
        await self.host.logout()
