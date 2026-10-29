import asyncio
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reolink_control_lab' / 'app'))
from catalog import Feature, build_catalog
from service import ControlService
from main import create_app, validate_options
from aiohttp.test_utils import TestClient, TestServer


class FakeHost:
    def __init__(self):
        self.capabilities = {'volume_speak', 'battery', 'motion_detection', 'snapshot', 'privacy_mode', 'siren_play'}
        self._capabilities = {0: {None: set(self.capabilities)}}
        self._battery = {0: {'batteryPercent': 77}}
        self.chime_list = []
        self.volume_value = 20
        self.writes = []
        self.uid = 'TEST_UID_NOT_REAL'
        self.baichuan = type('BC', (), {'GetAudioFileList': AsyncMock(), 'GetAutoReply': AsyncMock(),
                                       'unregister_callback': lambda *args: None})()

    def supported(self, channel, cap): return cap in self.capabilities
    async def get_host_data(self): pass
    async def get_states(self, **kwargs): pass
    async def logout(self): pass
    def doorbell_led_list(self, ch): return []
    def ai_supported_types(self, ch): return []
    def bit_rate_list(self, *args): return []
    def frame_rate_list(self, *args): return []
    def work_mode_battery_list(self, ch): return []
    def work_mode_powered_list(self, ch): return []
    def quick_reply_dict(self, ch): return {-1: 'off'}
    def post_recording_time_list(self, ch): return []
    def battery_percentage(self, ch): return 77
    def battery_temperature(self, ch): return 20
    def volume_speak(self, ch): return self.volume_value
    def md_sensitivity(self, ch): return 25
    def motion_detected(self, ch): return True
    async def set_volume(self, **kwargs):
        self.writes.append(kwargs)
        self.volume_value = kwargs['volume_speak']
    async def get_snapshot(self, channel): return b'\xff\xd8TEST\xff\xd9'


def options(**extra):
    return validate_options({'camera_name': 'Example', 'camera_address': '192.0.2.10',
                             'camera_username': 'admin', 'camera_password': 'EXAMPLE_SECRET', **extra})


class CatalogTests(unittest.TestCase):
    def test_real_capability_gates(self):
        keys = {f.key for f in build_catalog(FakeHost(), 0)}
        self.assertIn('volume_speak', keys)
        self.assertNotIn('recording', keys)
        self.assertNotIn('privacy', keys)
        self.assertNotIn('siren_short', keys)
        self.assertNotIn('auto_reply_file', keys)
        keys = {f.key for f in build_catalog(FakeHost(), 0, allow_risky=True)}
        self.assertIn('privacy', keys)
        self.assertIn('siren_short', keys)

    def test_input_validation(self):
        f = Feature('volume', 'Volume', 'number')
        for bad in (True, -1, 101, 'nan', '1.2', '__import__("os")'):
            with self.subTest(bad=bad), self.assertRaises(ValueError): f.validate(bad)
        self.assertEqual(f.validate('42'), 42)
        switch = Feature('test', 'Test', 'switch')
        self.assertFalse(switch.validate('OFF'))
        with self.assertRaises(ValueError): switch.validate('false')
        with self.assertRaises(ValueError): Feature('x', 'X', 'select', options=['Auto']).validate('Other')

    def test_poll_floor(self):
        with self.assertRaises(ValueError): options(poll_interval=1)
        with self.assertRaises(ValueError): options(read_only='false')


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.host = FakeHost()
        self.service = ControlService(options(), self.temp.name, self.host)
        await self.service.refresh(initial=True)

    async def asyncTearDown(self):
        await self.service.close()
        self.temp.cleanup()

    async def test_read_only_never_writes(self):
        with self.assertRaisesRegex(ValueError, 'Read-only'):
            await self.service.command('volume_speak', 50)
        self.assertEqual(self.host.writes, [])

    async def test_validate_before_network_and_read_back(self):
        self.service.options['read_only'] = False
        with self.assertRaises(ValueError): await self.service.command('volume_speak', 101)
        self.assertEqual(self.host.writes, [])
        await self.service.command('volume_speak', '45')
        self.assertEqual(self.host.writes, [{'channel': 0, 'volume_speak': 45}])
        self.assertEqual(self.service.values['volume_speak'], 45)

    async def test_no_arbitrary_command(self):
        self.service.options['read_only'] = False
        for key in ('baichuan.reboot', '__dict__', 'set_net_port', 'privacy'):
            with self.assertRaises(ValueError): await self.service.command(key, True)
        self.assertEqual(self.host.writes, [])

    async def test_events_unknown_until_enabled(self):
        self.assertIsNone(self.service.values['motion'])

    async def test_mqtt_discovery_does_not_leak_credentials(self):
        configs = self.service.discovery()
        serialized = json.dumps(configs)
        self.assertNotIn('EXAMPLE_SECRET', serialized)
        self.assertNotIn('TEST_UID_NOT_REAL', serialized)
        volume = next(v for v in configs.values() if v['name'] == 'Speaker volume')
        self.assertNotIn('command_topic', volume)
        self.service.options['read_only'] = False
        volume = next(v for v in self.service.discovery().values() if v['name'] == 'Speaker volume')
        self.assertIn('command_topic', volume)

    async def test_snapshot_is_not_retained(self):
        client = type('MQTT', (), {'publish': AsyncMock()})()
        self.service.client = client
        await self.service.take_snapshot()
        self.assertFalse(client.publish.call_args.kwargs['retain'])
        self.service.client = None

    async def test_csrf_and_ingress(self):
        async with TestClient(TestServer(create_app(self.service, dev=False))) as client:
            self.assertEqual((await client.get('/api/state')).status, 403)
        async with TestClient(TestServer(create_app(self.service, dev=True))) as client:
            data = await (await client.get('/api/state')).json()
            self.assertNotIn('EXAMPLE_SECRET', json.dumps(data))
            self.assertEqual((await client.post('/api/refresh', json={})).status, 403)
            response = await client.post('/api/refresh', json={}, headers={'X-Lab-CSRF': data['csrf']})
            self.assertEqual(response.status, 200)
            response = await client.post('/api/action/volume_speak', json={'value': 30}, headers={'X-Lab-CSRF': data['csrf']})
            self.assertEqual(response.status, 400)
            self.assertEqual(self.host.writes, [])

    async def test_webhook_source_is_camera_only(self):
        async with TestClient(TestServer(create_app(self.service, dev=True))) as client:
            response = await client.post(self.service.webhook_path, json={'uid': self.host.uid})
            self.assertEqual(response.status, 403)

    async def test_recording_search_is_bounded(self):
        with self.assertRaises(ValueError): await self.service.recordings(hours=25)

    async def test_existing_webhook_is_not_overwritten(self):
        self.service.options.update(enable_events=True, read_only=False)
        self.host.capabilities.add('bc_webhook')
        self.host.baichuan.send = AsyncMock(return_value='<body><HaCfg><enable>1</enable><url>http://example.invalid/owner</url></HaCfg></body>')
        await self.service.setup_events(18099)
        self.assertFalse(self.service.events_active)
        self.assertIn('already registered', self.service.errors['events'])
        self.assertEqual(self.host.baichuan.send.call_count, 1)
        self.assertEqual(self.host.baichuan.send.call_args.kwargs['cmd_id'], 806)

    async def test_webhook_restore_preserves_original_settings(self):
        self.service.webhook_url = 'http://example.invalid/ours'
        self.service.webhook_original = '<body><HaCfg><enable>1</enable><url>https://example.invalid/original</url><verify_cert>1</verify_cert></HaCfg></body>'
        self.host.baichuan.send = AsyncMock(side_effect=[
            '<body><HaCfg><url>http://example.invalid/ours</url></HaCfg></body>', 'OK'])
        await self.service.close()
        call = self.host.baichuan.send.call_args.kwargs
        self.assertEqual(call['cmd_id'], 807)
        self.assertEqual(call['body'].findtext('.//verify_cert'), '1')
        self.assertEqual(call['body'].findtext('.//url'), 'https://example.invalid/original')

    async def test_webhook_new_owner_is_left_alone(self):
        self.service.webhook_url = 'http://example.invalid/ours'
        self.service.webhook_original = '<body><HaCfg><enable>0</enable><url/></HaCfg></body>'
        self.host.baichuan.send = AsyncMock(return_value='<body><HaCfg><url>http://example.invalid/new-owner</url></HaCfg></body>')
        await self.service.close()
        self.assertEqual(self.host.baichuan.send.call_count, 1)

if __name__ == '__main__':
    unittest.main()
