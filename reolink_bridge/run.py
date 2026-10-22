"""Translate Home Assistant app options to Neolink and go2rtc configurations,

and supervise both processes to prevent connection storms and file descriptor leaks.
"""
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time

DEFAULT_RTSP_PORT = 28554
DEFAULT_API_PORT = 1984
DEFAULT_INTERNAL_PORT = 38554


def adjust_rlimits():
    """Increase the soft open file descriptor limit if permitted."""
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(65536, hard) if hard > 0 else 65536
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            print(f"RLIMIT_NOFILE updated: soft={target}, hard={hard}", flush=True)
    except Exception as exc:
        print(f"Note: RLIMIT_NOFILE adjustment skipped: {exc}", flush=True)


def quoted(value):
    return json.dumps(str(value), ensure_ascii=False)


def validate_options(options):
    name = options.get('camera_name', 'doorbell')
    if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
        raise ValueError('camera_name must contain only letters, numbers, underscore or hyphen')
    required = ('camera_uid', 'camera_username', 'camera_password', 'rtsp_username', 'rtsp_password')
    for key in required:
        if not isinstance(options.get(key), str) or not options[key]:
            raise ValueError(f'{key} is required')
    rtsp_port = options.get('rtsp_port', DEFAULT_RTSP_PORT)
    if isinstance(rtsp_port, bool) or not isinstance(rtsp_port, int) or not 1024 <= rtsp_port <= 65535:
        raise ValueError('rtsp_port must be an integer between 1024 and 65535')
    api_port = options.get('api_port', DEFAULT_API_PORT)
    if isinstance(api_port, bool) or not isinstance(api_port, int) or not 1024 <= api_port <= 65535:
        raise ValueError('api_port must be an integer between 1024 and 65535')
    stream = options.get('stream', 'subStream')
    if stream not in ('mainStream', 'subStream'):
        raise ValueError('stream must be mainStream or subStream')
    idle = options.get('disconnect_when_idle', True)
    if not isinstance(idle, bool):
        raise ValueError('disconnect_when_idle must be true or false')


def build_neolink_config(options, internal_port=DEFAULT_INTERNAL_PORT):
    validate_options(options)
    name = options.get('camera_name', 'doorbell')
    stream = options.get('stream', 'subStream')
    idle = options.get('disconnect_when_idle', True)

    lines = [
        'bind = "127.0.0.1"',
        f'bind_port = {internal_port}',
        '',
        '[[cameras]]',
        f'name = {quoted(name)}',
        f'username = {quoted(options["camera_username"])}',
        f'password = {quoted(options["camera_password"])}',
        f'uid = {quoted(options["camera_uid"])}',
        'discovery = "local"',
        'push_notifications = false',
        'use_splash = false',
        f'stream = {quoted(stream)}',
        f'idle_disconnect = {str(idle).lower()}',
    ]
    address = options.get('camera_address', '').strip()
    if address:
        lines.append(f'address = {quoted(address)}')
    lines += ['[cameras.pause]', 'on_client = true', '']
    return '\n'.join(lines)


def build_go2rtc_config(options, internal_port=DEFAULT_INTERNAL_PORT):
    validate_options(options)
    name = options.get('camera_name', 'doorbell')
    stream = options.get('stream', 'subStream')
    rtsp_port = options.get('rtsp_port', DEFAULT_RTSP_PORT)
    api_port = options.get('api_port', DEFAULT_API_PORT)
    rtsp_user = options.get('rtsp_username', '')
    rtsp_pass = options.get('rtsp_password', '')

    lines = [
        'api:',
        f'  listen: ":{api_port}"',
        '',
        'rtsp:',
        f'  listen: ":{rtsp_port}"',
    ]
    if rtsp_user and rtsp_pass:
        lines.extend([
            f'  username: {quoted(rtsp_user)}',
            f'  password: {quoted(rtsp_pass)}',
        ])
    lines.extend([
        '',
        'streams:',
        f'  {name}:',
        f'    - rtsp://127.0.0.1:{internal_port}/{name}/{stream}',
        f'  "{name}/{stream}":',
        f'    - rtsp://127.0.0.1:{internal_port}/{name}/{stream}',
    ])
    alt_stream = 'mainStream' if stream == 'subStream' else 'subStream'
    lines.extend([
        f'  "{name}/{alt_stream}":',
        f'    - rtsp://127.0.0.1:{internal_port}/{name}/{alt_stream}',
        ''
    ])
    return '\n'.join(lines)


def build_config(options, internal_port=DEFAULT_INTERNAL_PORT):
    """Backwards compatibility alias for build_neolink_config."""
    return build_neolink_config(options, internal_port=internal_port)


def check_port(port, label='Port'):
    """Catch a busy host port before service listeners start."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(('0.0.0.0', port))
        except OSError as exc:
            raise ValueError(
                f'Cannot bind {label} port {port}: {exc.strerror}. '
                f'Choose an unused port in the app configuration.'
            ) from exc


def supervise_processes(commands):
    procs = []

    def stop_all(signum=None, frame=None):
        for proc in procs:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass
        if signum is not None:
            sys.exit(0)

    signal.signal(signal.SIGTERM, stop_all)
    signal.signal(signal.SIGINT, stop_all)

    try:
        for cmd in commands:
            print(f"Starting process: {cmd[0]}", flush=True)
            p = subprocess.Popen(cmd)
            procs.append(p)

        while True:
            for p in procs:
                ret = p.poll()
                if ret is not None:
                    print(f"Process {p.args[0]} exited with code {ret}. Stopping remaining services.", flush=True)
                    stop_all()
                    return ret
            time.sleep(1)
    except Exception as exc:
        print(f"Supervisor error: {exc}", file=sys.stderr, flush=True)
        stop_all()
        return 1


def main():
    adjust_rlimits()

    try:
        options = json.loads(Path(os.environ.get('OPTIONS_PATH', '/data/options.json')).read_text(encoding='utf-8'))
        validate_options(options)

        rtsp_port = options.get('rtsp_port', DEFAULT_RTSP_PORT)
        api_port = options.get('api_port', DEFAULT_API_PORT)
        internal_port = int(os.environ.get('INTERNAL_RTSP_PORT', DEFAULT_INTERNAL_PORT))

        check_port(rtsp_port, 'RTSP')
        check_port(api_port, 'API')
        check_port(internal_port, 'Internal RTSP')

        neolink_cfg = build_neolink_config(options, internal_port=internal_port)
        go2rtc_cfg = build_go2rtc_config(options, internal_port=internal_port)

    except (ValueError, OSError, TypeError) as exc:
        print(f'Configuration error: {exc}', file=sys.stderr, flush=True)
        return 1

    neolink_path = Path(os.environ.get('CONFIG_PATH', '/data/neolink.toml'))
    go2rtc_path = Path(os.environ.get('GO2RTC_CONFIG_PATH', '/data/go2rtc.yaml'))

    neolink_path.parent.mkdir(parents=True, exist_ok=True)
    go2rtc_path.parent.mkdir(parents=True, exist_ok=True)

    os.umask(0o077)
    with open(neolink_path, 'w', encoding='utf-8') as f:
        f.write(neolink_cfg)
    os.chmod(neolink_path, 0o600)

    with open(go2rtc_path, 'w', encoding='utf-8') as f:
        f.write(go2rtc_cfg)
    os.chmod(go2rtc_path, 0o600)

    name = options.get('camera_name', 'doorbell')
    stream = options.get('stream', 'subStream')
    print('====================================================', flush=True)
    print(f'Reolink Stream Bridge starting (Neolink + go2rtc proxy)', flush=True)
    print(f'  External RTSP port: {rtsp_port}', flush=True)
    print(f'  Snapshot/API port:  {api_port}', flush=True)
    print(f'  Camera name:        {name} ({stream})', flush=True)
    print('', flush=True)
    print('Home Assistant Generic Camera configuration:', flush=True)
    print(f'  Stream Source:   rtsp://127.0.0.1:{rtsp_port}/{name}/{stream}', flush=True)
    print(f'  Still Image URL: http://127.0.0.1:{api_port}/api/frame.jpeg?src={name}', flush=True)
    print(f'  RTSP transport:  tcp', flush=True)
    print(f'  Username/Pass:   use rtsp_username / rtsp_password configured in this app', flush=True)
    print('====================================================', flush=True)

    neolink_bin = os.environ.get('NEOLINK_BIN', '/usr/local/bin/neolink')
    go2rtc_bin = os.environ.get('GO2RTC_BIN', '/usr/local/bin/go2rtc')

    commands = [
        [neolink_bin, 'rtsp', '--config', str(neolink_path)],
        [go2rtc_bin, '-config', str(go2rtc_path)]
    ]
    return supervise_processes(commands)


if __name__ == '__main__':
    sys.exit(main())
