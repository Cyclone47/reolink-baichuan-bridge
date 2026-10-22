"""Regression tests for configuration safety, go2rtc proxy mapping, and occupied ports."""
import importlib.util
from pathlib import Path
import socket
import tomllib
import unittest

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).resolve().parents[1] / 'reolink_bridge' / 'run.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def options(self):
        return {
            'camera_name': 'doorbell',
            'camera_uid': 'EXAMPLE_UID',
            'camera_username': 'admin',
            'camera_password': 'example-camera-password',
            'rtsp_username': 'viewer',
            'rtsp_password': 'example-stream-password',
            'rtsp_port': 28554,
            'api_port': 21984,
            'stream': 'subStream',
            'disconnect_when_idle': True,
        }

    def test_neolink_internal_config(self):
        cfg = tomllib.loads(bridge.build_neolink_config(self.options(), internal_port=38554))
        self.assertEqual(cfg['bind'], '127.0.0.1')
        self.assertEqual(cfg['bind_port'], 38554)
        self.assertEqual(cfg['cameras'][0]['password'], 'example-camera-password')
        self.assertEqual(cfg['cameras'][0]['uid'], 'EXAMPLE_UID')
        self.assertFalse(cfg['cameras'][0]['push_notifications'])
        self.assertTrue(cfg['cameras'][0]['idle_disconnect'])
        self.assertTrue(cfg['cameras'][0]['pause']['on_client'])

    def test_go2rtc_config_mapping(self):
        raw = bridge.build_go2rtc_config(self.options(), internal_port=38554)
        self.assertIn('listen: ":28554"', raw)
        self.assertIn('listen: ":21984"', raw)
        self.assertIn('username: "viewer"', raw)
        self.assertIn('password: "example-stream-password"', raw)
        self.assertIn('rtsp://127.0.0.1:38554/doorbell/subStream', raw)
        self.assertIn('doorbell:', raw)
        self.assertIn('"doorbell/subStream":', raw)

    def test_custom_ports_preserved(self):
        opts = {**self.options(), 'rtsp_port': 18554, 'api_port': 2984}
        raw = bridge.build_go2rtc_config(opts, internal_port=39999)
        self.assertIn('listen: ":18554"', raw)
        self.assertIn('listen: ":2984"', raw)
        self.assertIn('rtsp://127.0.0.1:39999/doorbell/subStream', raw)

    def test_password_roundtrip(self):
        password = 'quotes" and slash\\ and newline\n and unicode\u00e9'
        options = {**self.options(), 'camera_password': password, 'rtsp_password': password}
        neocfg = tomllib.loads(bridge.build_neolink_config(options))
        self.assertEqual(neocfg['cameras'][0]['password'], password)
        go2cfg = bridge.build_go2rtc_config(options)
        self.assertIn('unicode\u00e9', go2cfg)

    def test_missing_credentials_rejected(self):
        for key in ('camera_uid', 'camera_password', 'rtsp_password'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                bridge.build_neolink_config({**self.options(), key: ''})

    def test_busy_port_has_actionable_error(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('0.0.0.0', 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            self.assertFalse(bridge.is_port_free(port))
            with self.assertRaisesRegex(ValueError, f'Cannot bind RTSP port {port}'):
                bridge.check_port(port, 'RTSP')


if __name__ == '__main__':
    unittest.main()
