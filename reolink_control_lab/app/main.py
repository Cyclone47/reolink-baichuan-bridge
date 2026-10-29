"""Ingress-only UI and camera-source-restricted webhook endpoint."""
import asyncio
import ipaddress
import json
import logging
import os
from pathlib import Path
import sys

from aiohttp import web
from service import ControlService


def validate_options(options):
    for key in ('camera_address', 'camera_username', 'camera_password'):
        if not isinstance(options.get(key), str) or not options[key]:
            raise ValueError(key + ' is required')
    # Literal LAN IP keeps webhook source validation unambiguous; no broad DNS trust.
    ipaddress.ip_address(options['camera_address'])
    for key, default in [('read_only', True), ('allow_disruptive_actions', False), ('enable_events', False),
                         ('replace_existing_webhook', False), ('mqtt_tls', False)]:
        value = options.get(key, default)
        if not isinstance(value, bool):
            raise ValueError(key + ' must be a boolean')
        options[key] = value
    for key, default, low, high in [('camera_channel', 0, 0, 63), ('mqtt_port', 1883, 1, 65535),
                                  ('poll_interval', 0, 0, 86400)]:
        value = options.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError('Invalid ' + key)
        options[key] = value
    if 0 < options['poll_interval'] < 60:
        raise ValueError('poll_interval must be 0 (manual) or at least 60 seconds')
    return options


def create_app(service, dev=False):
    @web.middleware
    async def authorize(request, handler):
        if request.path == service.webhook_path:
            if request.remote != service.options['camera_address'] or not service.webhook_url:
                raise web.HTTPForbidden()
        else:
            allowed = {'172.30.32.2'}
            if dev:
                allowed |= {'127.0.0.1', '::1'}
            if request.remote not in allowed:
                raise web.HTTPForbidden(text='Use Home Assistant Ingress.')
            if request.method == 'POST' and request.headers.get('X-Lab-CSRF') != service.csrf:
                raise web.HTTPForbidden(text='Reload the control panel and retry.')
        try:
            return await handler(request)
        except (web.HTTPException, asyncio.CancelledError):
            raise
        except Exception as exc:
            return web.json_response({'ok': False, 'error': service.redact(exc)}, status=400)

    app = web.Application(middlewares=[authorize], client_max_size=1024 * 1024)

    async def index(request):
        return web.FileResponse(Path(__file__).with_name('index.html'))

    async def state(request):
        response = web.json_response({**service.metadata(), 'csrf': service.csrf})
        response.headers['Cache-Control'] = 'no-store'
        return response

    async def refresh(request):
        return web.json_response(await service.refresh())

    async def action(request):
        data = await request.json()
        if not isinstance(data, dict) or set(data) - {'value'}:
            raise ValueError('Expected an object containing only value')
        return web.json_response(await service.command(request.match_info['key'], data.get('value')))

    async def snapshot(request):
        if request.method == 'POST':
            await service.take_snapshot()
        if not service.snapshot:
            raise web.HTTPNotFound(text='Take a snapshot first.')
        return web.Response(body=service.snapshot, content_type='image/jpeg', headers={'Cache-Control': 'no-store'})

    async def recordings(request):
        data = await request.json()
        return web.json_response({'recordings': await service.recordings(data.get('hours', 24))})

    async def webhook(request):
        data = await request.read()
        parsed = json.loads(data)
        if not isinstance(parsed, dict) or parsed.get('uid') != service.host.uid:
            raise web.HTTPBadRequest()
        service.host.baichuan.webhook_push_callback(data)
        return web.Response(text='OK')

    app.router.add_get('/', index)
    app.router.add_get('/api/state', state)
    app.router.add_post('/api/refresh', refresh)
    app.router.add_post('/api/action/{key}', action)
    app.router.add_get('/api/snapshot', snapshot)
    app.router.add_post('/api/snapshot', snapshot)
    app.router.add_post('/api/recordings', recordings)
    app.router.add_post(service.webhook_path, webhook)
    return app


async def serve(options, port, dev=False):
    service = ControlService(options, os.environ.get('LAB_DATA_DIR', '/data'))
    app = create_app(service, dev)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, '127.0.0.1' if dev else '0.0.0.0', port).start()
    print(f'Control Lab listening on Ingress port {port}; read_only={options["read_only"]}', flush=True)
    try:
        await service.start()
        try:
            await service.setup_events(port)
        except Exception as exc:
            service.errors['events'] = service.redact(exc)
        await asyncio.Event().wait()
    finally:
        await asyncio.wait_for(service.close(), 20)
        await runner.cleanup()


async def ingress_port():
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get('http://supervisor/addons/self/info', headers={
                'Authorization': 'Bearer ' + os.environ['SUPERVISOR_TOKEN']}, timeout=aiohttp.ClientTimeout(total=10)) as response:
            response.raise_for_status()
            return (await response.json())['data']['ingress_port']


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    # Upstream debug logs can contain identifiers and raw camera responses.
    logging.getLogger('reolink_aio').setLevel(logging.CRITICAL)
    options = validate_options(json.loads(Path(os.environ.get('OPTIONS_PATH', '/data/options.json')).read_text()))
    dev = os.environ.get('LAB_DEV_MODE') == '1'
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    port = int(os.environ.get('LAB_PORT', '18099')) if dev else asyncio.run(ingress_port())
    try:
        asyncio.run(serve(options, port, dev))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
