"""End-to-end MQTT tests against an ephemeral loopback-only broker."""
import asyncio
import socket
import tempfile
import unittest
import sys

import aiomqtt
from amqtt.broker import Broker
from test_control_lab import FakeHost, options
from service import ControlService

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def eventually(predicate, timeout=6):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.05)


class MqttIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_commands_retained_replay_and_shutdown(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        broker = Broker({'listeners': {'default': {'type': 'tcp', 'bind': f'127.0.0.1:{port}'}},
                         'plugins': {'amqtt.plugins.authentication.AnonymousAuthPlugin': {'allow_anonymous': True}}})
        await broker.start()
        temp = tempfile.TemporaryDirectory()
        host = FakeHost()
        service = ControlService(options(read_only=False, mqtt_host='127.0.0.1', mqtt_port=port), temp.name, host)
        await service.refresh(initial=True)
        seen = {}
        try:
            async with aiomqtt.Client('127.0.0.1', port=port) as observer:
                await observer.subscribe('homeassistant/#')
                await observer.subscribe(service.base + '/#')

                async def collect():
                    async for message in observer.messages:
                        seen[str(message.topic)] = bytes(message.payload).decode(errors='replace')

                collect_task = asyncio.create_task(collect())
                await observer.publish(service.base + '/set/volume_speak', '99', retain=True)
                service.tasks.append(asyncio.create_task(service.mqtt_loop()))
                await eventually(lambda: seen.get(service.base + '/availability') == 'online')
                self.assertEqual(host.volume_value, 20, 'Retained command replay changed the device')
                configs = {k: v for k, v in seen.items() if k.startswith('homeassistant/') and k.endswith('/config')}
                self.assertTrue(any('/number/' in k for k in configs))
                self.assertFalse(any('EXAMPLE_SECRET' in v for v in seen.values()))
                await observer.publish(service.base + '/set/volume_speak', '55')
                await eventually(lambda: host.volume_value == 55)
                await observer.publish(service.base + '/set/volume_speak', '101')
                await eventually(lambda: service.base + '/result' in seen)
                self.assertEqual(host.volume_value, 55)
                self.assertEqual(len(host.writes), 1)
                await service.close()
                await eventually(lambda: seen.get(service.base + '/availability') == 'offline')
                collect_task.cancel()
                await asyncio.gather(collect_task, return_exceptions=True)
        finally:
            if not service.closed:
                await service.close()
            await broker.shutdown()
            temp.cleanup()


if __name__ == '__main__':
    unittest.main()
