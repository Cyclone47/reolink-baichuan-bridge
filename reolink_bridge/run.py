"""Translate Home Assistant app options to a private Neolink configuration."""
import json
import os
from pathlib import Path
import re
import sys

def quoted(value):
    return json.dumps(str(value), ensure_ascii=False)

def build_config(options):
    name = options.get('camera_name', 'doorbell')
    if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
        raise ValueError('camera_name must contain only letters, numbers, underscore or hyphen')
    required = ('camera_uid', 'camera_username', 'camera_password', 'rtsp_username', 'rtsp_password')
    for key in required:
        if not isinstance(options.get(key), str) or not options[key]:
            raise ValueError(f'{key} is required')
    port = options.get('rtsp_port', 18554)
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError('rtsp_port must be an integer between 1024 and 65535')
    stream = options.get('stream', 'subStream')
    if stream not in ('mainStream', 'subStream'):
        raise ValueError('stream must be mainStream or subStream')
    idle = options.get('disconnect_when_idle', True)
    if not isinstance(idle, bool):
        raise ValueError('disconnect_when_idle must be true or false')
    lines = ['bind = "0.0.0.0"', f'bind_port = {port}', '', '[[users]]',
             f'name = {quoted(options["rtsp_username"])}', f'pass = {quoted(options["rtsp_password"])}',
             '', '[[cameras]]', f'name = {quoted(name)}',
             f'username = {quoted(options["camera_username"])}',
             f'password = {quoted(options["camera_password"])}',
             f'uid = {quoted(options["camera_uid"])}',
             'discovery = "local"', 'push_notifications = false', 'use_splash = false',
             f'stream = {quoted(stream)}', f'idle_disconnect = {str(idle).lower()}',
             f'permitted_users = [{quoted(options["rtsp_username"])}]']
    address = options.get('camera_address', '').strip()
    if address:
        lines.append(f'address = {quoted(address)}')
    lines += ['[cameras.pause]', 'on_client = true', '']
    return '\n'.join(lines)

def main():
    try:
        options = json.loads(Path(os.environ.get('OPTIONS_PATH', '/data/options.json')).read_text())
        config = build_config(options)
    except (ValueError, OSError, TypeError) as exc:
        print(f'Configuration error: {exc}', file=sys.stderr)
        return 1
    path = Path(os.environ.get('CONFIG_PATH', '/data/neolink.toml'))
    path.parent.mkdir(parents=True, exist_ok=True)
    os.umask(0o077)
    with open(path, 'w', encoding='utf-8') as file:
        file.write(config)
    os.chmod(path, 0o600)
    print(f'Local stream bridge starting on RTSP port {options.get("rtsp_port", 18554)}.', flush=True)
    os.execv('/usr/local/bin/neolink', ['neolink', 'rtsp', '--config', str(path)])

if __name__ == '__main__':
    sys.exit(main())
