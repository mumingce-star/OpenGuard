#!/usr/bin/env python3
"""Opt-in, local Docker launcher for synthetic P1 integration (stdlib only).

Never discovers production configuration, pulls images, or removes containers.
Run from any directory; roots are confined to this checkout's ignored output.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

REPOSITORY = Path(__file__).resolve().parents[1]
LABEL = 'org.openguard.p1-dev'
PYTHON = '/opt/api/bin/python'
RESERVED_PORTS = {5174, 8011, 8080, 8000}
IDENTITY_HEADER = 'X-OpenGuard-Dev-Identity'
ACCEPTANCE_PREFIX = 'p1-frontend-acceptance-'


def server_module(root):
    return 'app.frontend_acceptance_server' if root.name.startswith(ACCEPTANCE_PREFIX) else 'app.dev_integration_server'


def seed_version(root):
    return 'p1-frontend-acceptance/1' if root.name.startswith(ACCEPTANCE_PREFIX) else 'p1-dev-integration/2'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LaunchError('health redirect refused')

class LaunchError(RuntimeError):
    pass


def safe_root(value, repository=REPOSITORY):
    raw = Path(value)
    if '..' in raw.parts:
        raise LaunchError('parent traversal is not allowed')
    path = raw if raw.is_absolute() else repository / raw
    if not re.fullmatch(r'(?:p1-dev-|p1-frontend-acceptance-)[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', path.name):
        raise LaunchError('root name must identify a dev or frontend-acceptance instance')
    if path.parent != repository / 'output' / 'manual-fixes':
        raise LaunchError('root must be a direct child of this checkout output/manual-fixes')
    for p in [path, *path.parents]:
        if p.is_symlink():
            raise LaunchError('symlink paths are forbidden')
    if path.exists():
        info = path.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise LaunchError('existing root must be an owned private directory')
    return path


def port_number(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise LaunchError('invalid port') from None
    if not 1024 <= port <= 65535 or port in RESERVED_PORTS:
        raise LaunchError('choose an unprivileged, non-existing-service port')
    return port


def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(('127.0.0.1', port))
        except OSError as error:
            raise LaunchError('loopback port unavailable; no process was stopped') from error


def docker(*args, timeout=40):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise LaunchError('Docker command failed: ' + result.stderr.strip()[:2000])
    return result.stdout.strip()


def inspect_owned(name):
    # A failed inspect is never interpreted as absence: list exact names first.
    names = docker('container', 'ls', '-a', '--format', '{{.Names}}').splitlines()
    if name not in names:
        return None
    # Select only non-secret runtime identity fields, never the full environment.
    def fields(prefix, names):
        return ','.join('"' + key + '":{{json .' + prefix + key + '}}' for key in names)
    value = docker('inspect', '--format', '{' + fields('', ('Id', 'Image', 'Mounts')) +
        ',"State":{' + fields('State.', ('Running', 'Status')) + '},"Config":{' +
        fields('Config.', ('Labels', 'User', 'WorkingDir', 'Entrypoint', 'Cmd')) + '},"HostConfig":{' +
        fields('HostConfig.', ('PortBindings', 'ReadonlyRootfs', 'CapDrop', 'CapAdd', 'SecurityOpt',
            'Privileged', 'NetworkMode', 'PublishAllPorts', 'PidMode', 'IpcMode', 'UTSMode',
            'Devices', 'DeviceRequests', 'ExtraHosts', 'PidsLimit', 'NanoCpus', 'Memory',
            'Tmpfs', 'RestartPolicy')) + '}}', name)
    return json.loads(value)


def marker(root):
    path = root / ('frontend-acceptance-manifest.json' if root.name.startswith(ACCEPTANCE_PREFIX) else 'dev-manifest.json')
    if path.is_symlink() or not path.is_file():
        if root.name.startswith(ACCEPTANCE_PREFIX):
            raise LaunchError('acceptance_not_prepared')
        raise LaunchError('initialized manifest is required; run init explicitly')
    try:
        value = json.loads(path.read_text())
    except (ValueError, OSError):
        raise LaunchError('manifest is unreadable') from None
    if value.get('synthetic') is not True or not value.get('root_id'):
        raise LaunchError('not a synthetic P1 instance')
    if root.name.startswith(ACCEPTANCE_PREFIX) and value.get('seed_version') != seed_version(root):
        raise LaunchError('acceptance seed version mismatch')
    return value


def identity(root, manifest):
    root_hash = hashlib.sha256(str(root).encode()).hexdigest()
    instance = manifest['root_id']
    if not isinstance(instance, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', instance):
        raise LaunchError('invalid instance identity')
    prefix = 'openguard-p1-acceptance-' if root.name.startswith(ACCEPTANCE_PREFIX) else 'openguard-p1-dev-'
    return prefix + root_hash[:16], {LABEL: instance, LABEL + '.root': root_hash}


def check_owned(info, labels):
    actual = info['Config'].get('Labels') or {}
    if any(actual.get(k) != v for k, v in labels.items()):
        raise LaunchError('container identity mismatch; refusing to stop/start')
    if not re.fullmatch(r'[0-9a-f]{64}', info.get('Id', '')):
        raise LaunchError('container identity mismatch; full actual ID required')


def serve_command(root, api_port, web_port):
    return ['-B', '-m', server_module(root), 'serve', '--root',
            '/workspace/output/manual-fixes/' + root.name, '--port', '18011',
            '--web-port', str(web_port), '--api-origin-port', str(api_port)]


def check_start_configuration(info, container_id, root, image_id, api_port, web_port):
    """Compare selected effective facts, not labels or the whole HostConfig."""
    config, host = info.get('Config', {}), info.get('HostConfig', {})
    def require(condition, field):
        if not condition:
            raise LaunchError('container configuration mismatch: ' + field + '; preserve and inspect manually')
    require(info.get('Id') == container_id, 'Id')
    require(info.get('Image') == image_id, 'Image')
    require(config.get('User') in {'0', '0:0'}, 'User')
    require(config.get('WorkingDir') == '/workspace', 'WorkingDir')
    require(config.get('Entrypoint') == [PYTHON], 'Entrypoint')
    require(config.get('Cmd') == serve_command(root, api_port, web_port), 'Cmd')
    bindings = host.get('PortBindings') or {}
    require(bindings == {'18011/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(api_port)}]}, 'PortBindings')
    require(host.get('ReadonlyRootfs') is True, 'ReadonlyRootfs')
    require({s.upper().removeprefix('CAP_') for s in host.get('CapDrop') or []} == {'ALL'}, 'CapDrop')
    require(not host.get('CapAdd'), 'CapAdd')
    options = {s.replace(':', '=') for s in host.get('SecurityOpt') or []}
    require(options in ({'no-new-privileges'}, {'no-new-privileges=true'}), 'SecurityOpt')
    require(host.get('Privileged') is False and host.get('PublishAllPorts') is False, 'privileged/publish-all')
    require(host.get('NetworkMode') in {'default', 'bridge'}, 'NetworkMode')
    require(host.get('IpcMode') in {'', 'private'} and not host.get('PidMode') and not host.get('UTSMode'), 'namespaces')
    for field in ('Devices', 'DeviceRequests', 'ExtraHosts'):
        require(not host.get(field), field)
    for field, expected in (('PidsLimit', 128), ('NanoCpus', 2_000_000_000), ('Memory', 1_073_741_824)):
        require(host.get(field) == expected, field)
    require((host.get('RestartPolicy') or {}).get('Name', 'no') in {'', 'no'}, 'RestartPolicy')
    tmpfs = host.get('Tmpfs') or {}
    require(set(tmpfs) == {'/tmp'}, 'Tmpfs')
    options = set(tmpfs['/tmp'].split(','))
    require({'rw', 'nosuid', 'nodev', 'noexec'} <= options and
            options - {'rw', 'nosuid', 'nodev', 'noexec'} in ({'size=64m'}, {'size=67108864'}, {'size=65536k'}), 'tmpfs options')
    expected = {(str(REPOSITORY / part), '/workspace/' + part, False)
                for part in ('backend', 'rules', 'schemas', 'examples', 'tests/fixtures')}
    expected.add((str(root), '/workspace/output/manual-fixes/' + root.name, True))
    mounts = info.get('Mounts') or []
    require(len(mounts) == len(expected), 'mount count')
    require(all(m.get('Type') == 'bind' and m.get('Propagation') in {'', 'rprivate'} for m in mounts), 'mount type/propagation')
    actual = {(m.get('Source'), m.get('Destination'), m.get('RW')) for m in mounts}
    require(actual == expected, 'source/data mounts')


def check_acceptance_configuration(info, root, manifest):
    """Reuse start's full safety contract before any acceptance exec."""
    check_owned(info, identity(root, manifest)[1])
    image = info.get('Image', '')
    if not isinstance(image, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise LaunchError('invalid actual runtime Image')
    try:
        ports = []
        for key in ('api_base', 'recommended_web_origin'):
            value = urllib.parse.urlsplit(manifest[key])
            if value.scheme != 'http' or value.hostname != '127.0.0.1' or value.path or value.query or value.fragment or value.username:
                raise ValueError()
            ports.append(port_number(value.port))
        api_port, web_port = ports
        if api_port == web_port:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise LaunchError('invalid acceptance endpoint configuration') from None
    labels = identity(root, manifest)[1]
    labels[LABEL+'.config'] = hashlib.sha256(json.dumps([image,api_port,web_port]).encode()).hexdigest()
    check_owned(info, labels)
    check_start_configuration(info, info['Id'], root, image, api_port, web_port)
    return image


def validate_acceptance(root, image_id, platform):
    """Read-only SQL in the verified live instance, or an offline RO data bind.

    A live WAL may need its existing namespace's SHM coordination. Never use
    immutable=1 (which can ignore WAL), copy a live DB, or checkpoint to validate.
    """
    manifest = marker(root)
    info = inspect_owned(identity(root, manifest)[0])
    if info and info['State']['Running']:
        actual = check_acceptance_configuration(info, root, manifest)
        if actual != image_id:
            raise LaunchError('container configuration mismatch: Image')
        return json.loads(docker('exec', info['Id'], PYTHON, '-B', '-m',
            'app.frontend_acceptance_server', 'validate', '--root',
            '/workspace/output/manual-fixes/' + root.name, timeout=90))
    args = common_args(root, image_id, platform)
    args[-1] += ',readonly'  # common_args ends with the sole data bind
    value = docker('run', '--rm', '--network=none', *args, image_id,
        '-B', '-m', 'app.frontend_acceptance_server', 'validate', '--root',
        '/workspace/output/manual-fixes/' + root.name, timeout=90)
    return json.loads(value)


def health_identity(response, manifest):
    expected = {k: manifest.get(k) for k in ('root_id', 'synthetic', 'seed_version')}
    try:
        observed = json.loads(response.headers.get(IDENTITY_HEADER, ''))
    except (ValueError, TypeError):
        raise LaunchError('health identity missing/invalid') from None
    if (expected['synthetic'] is not True or expected['seed_version'] not in {'p1-dev-integration/2', 'p1-frontend-acceptance/1'}
            or not isinstance(observed, dict) or observed.get('synthetic') is not True
            or observed != expected):
        raise LaunchError('health identity mismatch')
    return observed


def wait_healthy(name, labels, container_id, root, image_id, api_port, web_port, manifest):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for _ in range(60):
        current = inspect_owned(name)
        if not current:
            break
        check_owned(current, labels)
        check_start_configuration(current, container_id, root, image_id, api_port, web_port)
        if not current['State']['Running']:
            break
        try:
            with opener.open(f'http://127.0.0.1:{api_port}/api/v1/scans?limit=1', timeout=1) as response:
                if response.status == 200:
                    observed = health_identity(response, manifest)
                    after = inspect_owned(name)
                    if not after:
                        raise LaunchError('container disappeared during health check')
                    check_owned(after, labels)
                    check_start_configuration(after, container_id, root, image_id, api_port, web_port)
                    if not after['State']['Running']:
                        raise LaunchError('container stopped during health check')
                    binding = after['HostConfig']['PortBindings']['18011/tcp'][0]
                    return {'state': 'running', 'container': name, 'container_id': container_id,
                            'image': after['Image'], 'observed_identity': observed,
                            'api': 'http://' + binding['HostIp'] + ':' + binding['HostPort'],
                            'ports': after['HostConfig']['PortBindings'], 'synthetic': True}
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    raise LaunchError('startup health failed')


def local_image(image):
    if not image:
        raise LaunchError('--image is required for init/start; use an inspected local runtime image')
    raw = json.loads(docker('image', 'inspect', '--format', '{"Id":{{json .Id}},"Os":{{json .Os}},"Architecture":{{json .Architecture}}}', image))
    if (raw.get('Os') != 'linux' or raw.get('Architecture') not in {'amd64', 'arm64'}
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', raw.get('Id', ''))):
        raise LaunchError('unsupported local image platform')
    return raw['Id'], 'linux/' + raw['Architecture']


def common_args(root, image_id, platform):
    # Docker Desktop maps this private bind root to uid 0. Retain strict
    # ownership checks; isolated container root has all capabilities dropped.
    args = ['--pull=never', '--platform', platform, '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--pids-limit=128', '--cpus=2', '--memory=1g',
            '--user', '0:0', '--workdir', '/workspace',
            '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=64m',
            '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONPATH=/workspace/backend',
            '--entrypoint', PYTHON]
    # Only public source inputs; never the whole checkout/output, .env, .git or user home.
    for part in ('backend', 'rules', 'schemas', 'examples', 'tests/fixtures'):
        args += ['--mount', f'type=bind,source={REPOSITORY / part},target=/workspace/{part},readonly']
    args += ['--mount', f'type=bind,source={root},target=/workspace/output/manual-fixes/{root.name}']
    return args


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'start', 'status', 'stop', 'graph-ref'])
    parser.add_argument('--root', required=True)
    parser.add_argument('--image')
    parser.add_argument('--api-port', type=port_number, default=18011)
    parser.add_argument('--web-port', type=port_number, default=15174)
    args = parser.parse_args(argv)
    root = safe_root(args.root)
    inside = '/workspace/output/manual-fixes/' + root.name
    if args.api_port == args.web_port:
        raise LaunchError('API and web ports must differ')
    if args.action == 'init':
        if root.exists() and any(root.iterdir()):
            raise LaunchError('init refuses an existing nonempty space; preserve it and choose a new name')
        image_id, platform = local_image(args.image)
        root.parent.mkdir(parents=True, exist_ok=True)
        root.mkdir(mode=0o700, exist_ok=True)
        version = subprocess.check_output(['git', '-C', str(REPOSITORY), 'rev-parse', 'HEAD'], text=True).strip()
        print(docker('run', '--rm', '--network=none', *common_args(root, image_id, platform), image_id,
                     '-B', '-m', server_module(root), 'init', '--root', inside,
                     '--code-version', version, timeout=90))
        return
    manifest = marker(root)
    name, labels = identity(root, manifest)
    if args.action == 'graph-ref':
        # Captured by the existing helper during explicit seed, never guessed client-side.
        print(json.dumps(manifest.get('graph_refs'), ensure_ascii=False, indent=2))
        return
    info = inspect_owned(name)
    if info:
        check_owned(info, labels)
    if args.action == 'status':
        print(json.dumps({'instance_id': manifest['root_id'], 'container': name,
                          'state': info['State']['Status'] if info else 'not_started',
                          'root': str(root), 'synthetic': True,
                          'ports': info['HostConfig'].get('PortBindings', {}) if info else {}}, indent=2))
        return
    if args.action == 'stop':
        if info and info['State']['Running']:
            print(docker('stop', '--time', '15', info['Id'], timeout=25))
        else:
            print('already stopped; no unrelated process touched')
        return
    image_id, platform = local_image(args.image)
    if root.name.startswith(ACCEPTANCE_PREFIX):
        validated = validate_acceptance(root, image_id, platform)
        if validated != manifest:
            raise LaunchError('acceptance manifest changed during validation')
    config_hash = hashlib.sha256(json.dumps([image_id, args.api_port, args.web_port]).encode()).hexdigest()
    labels[LABEL + '.config'] = config_hash
    if info:
        check_owned(info, labels)
        if info['State']['Running']:
            raise LaunchError('instance already running; duplicate start refused')
        check_start_configuration(info, info['Id'], root, image_id, args.api_port, args.web_port)
    check_port(args.api_port)
    if info:
        container_id = info['Id']
        docker('start', container_id)
    else:
        label_args = [v for k, value in labels.items() for v in ('--label', k + '=' + value)]
        container_id = docker('run', '-d', '--name', name, *label_args,
               '--network=bridge',
               '--publish', f'127.0.0.1:{args.api_port}:18011',
               *common_args(root, image_id, platform), image_id,
               *serve_command(root, args.api_port, args.web_port))
    try:
        result = wait_healthy(name, labels, container_id, root, image_id, args.api_port, args.web_port, manifest)
    except Exception:
        # Ownership-only cleanup: a broken safety setting must not prevent stop.
        current = inspect_owned(name)
        if current:
            check_owned(current, identity(root, manifest)[1])
            if current['Id'] != container_id:
                raise LaunchError('container replaced; refusing cleanup of a different ID') from None
            if current['State']['Running']:
                docker('stop', '--time', '15', container_id, timeout=25)
        raise
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except (LaunchError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
