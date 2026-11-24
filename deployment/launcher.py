"""Package-relative TEST_ONLY deployment; no old accounts, ledgers or service reuse."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.metadata
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit
import venv

ROOT = Path(__file__).resolve().parents[1]
APPLICATION = ROOT / 'application'
RUNTIME = ROOT / 'runtime'
if os.environ.get('OPENGUARD_PACKAGE_SELFTEST_ROOT'):
    _test_root = Path(os.environ['OPENGUARD_PACKAGE_SELFTEST_ROOT'])
    if not _test_root.is_absolute() or not _test_root.resolve().is_relative_to(RUNTIME / 'self-tests'):
        raise RuntimeError('Self-test storage must be inside this package runtime/self-tests')
    RUNTIME = _test_root
MODEL_NAME = 'qwen3:4b-instruct-2507-q4_K_M'
LOCAL_MODEL_ORIGIN = 'http://127.0.0.1:11434'
DOCKER_MODEL_ORIGIN = 'http://host.docker.internal:11434'
DOCKER_GATEWAY_NETWORKS = tuple(
    ipaddress.ip_network(network) for network in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')
)
MODEL_MANIFEST = '0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0'
MODEL_WEIGHT = '85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9'
OLLAMA_VERSION = '0.33.3'
BUNDLE_SHA = 'b4d28764503ce135702d948878d8604495fd0addf38c7a070892e93d038c714b'
LICENSE_SHA = 'accfc4d5a588384b29c4817392854afb8f319b4568359ca8d063df8a9bc396b6'
REVISION = '0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b'


@dataclass(frozen=True)
class DeploymentSettings:
    container_mode: bool
    ollama_docker_host: bool


def deployment_settings():
    container = os.environ.get('OPENGUARD_CONTAINER_MODE', '0')
    docker_host = os.environ.get('OPENGUARD_OLLAMA_DOCKER_HOST', '0')
    if container not in {'0', '1'}:
        raise RuntimeError('OPENGUARD_CONTAINER_MODE 只允许 0 或 1。')
    if docker_host not in {'0', '1'}:
        raise RuntimeError('OPENGUARD_OLLAMA_DOCKER_HOST 只允许 0 或 1。')
    if container == '0' and docker_host == '1':
        raise RuntimeError('仅在容器模式下可启用 OPENGUARD_OLLAMA_DOCKER_HOST。')
    return DeploymentSettings(container == '1', docker_host == '1')


def validate_listener(host):
    settings = deployment_settings()
    if host != '127.0.0.1' and not (settings.container_mode and host == '0.0.0.0'):
        raise RuntimeError('监听地址仅允许 127.0.0.1；容器模式也允许 0.0.0.0。')


def utc():
    return datetime.now(timezone.utc).isoformat()


def file_hash(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def require_platform():
    if sys.implementation.name != 'cpython' or sys.version_info[:2] != (3, 12):
        raise RuntimeError('需要CPython 3.12；请使用 python3.12 openguard.py ...，不自动改动系统Python。')
    if os.name != 'posix' or platform.system() not in {'Darwin', 'Linux'}:
        raise RuntimeError('支持macOS/Linux；Windows须在WSL2 Linux内运行，不支持原生Windows解释器。')


def private_dir(path):
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise RuntimeError('运行目录必须归当前用户所有且权限为700：' + str(path))
    return path


def _runtime_python_selection():
    settings = deployment_settings()
    candidate = RUNTIME / 'venv/bin/python'
    has_package_venv = candidate.is_file() and os.access(candidate, os.X_OK)
    if has_package_venv and not settings.container_mode:
        return candidate, False
    override = os.environ.get('OPENGUARD_PYTHON')
    if override is not None:
        executable = Path(override)
        if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError('OPENGUARD_PYTHON 必须指向可执行解释器的绝对路径。')
        return executable, True
    return (candidate if has_package_venv else Path(sys.executable)), False


def runtime_python():
    executable, override = _runtime_python_selection()
    if override and not dependency_report(executable)['ready']:
        raise RuntimeError('OPENGUARD_PYTHON 未满足 CPython 3.12 及固定依赖要求。')
    return executable


def pins():
    return dict(line.split('==', 1) for line in (ROOT / 'deployment/requirements.lock').read_text().splitlines()
                if line and not line.startswith('#'))


def dependency_report(executable=None):
    executable = Path(executable) if executable is not None else _runtime_python_selection()[0]
    code = ('import importlib.metadata as m,json,sys; p=json.loads(sys.argv[1]); r={}; '
            '\nfor n,v in p.items():\n try: a=m.version(n)\n except m.PackageNotFoundError: a=None\n r[n]={"expected":v,"actual":a,"match":a==v}'
            '\nprint(json.dumps({"python":sys.executable,"version":list(sys.version_info[:3]),"implementation":sys.implementation.name,"packages":r}))')
    result = subprocess.run([str(executable), '-B', '-c', code, json.dumps(pins())],
                            text=True, capture_output=True, check=True, timeout=30)
    report = json.loads(result.stdout)
    report['ready'] = (report.pop('implementation') == 'cpython' and report['version'][:2] == [3, 12]
                       and all(x['match'] for x in report['packages'].values()))
    return report


def sample_report():
    items = [ ('http-server.bundle',462976,BUNDLE_SHA), ('http-server-LICENSE.txt',1124,LICENSE_SHA) ]
    report = []
    for name,size,digest in items:
        path = ROOT/'samples'/name
        info = path.lstat()
        valid = stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and info.st_size == size
        actual = file_hash(path) if valid else None
        report.append({'name':name,'bytes':info.st_size,'sha256':actual,'match':valid and actual == digest})
    return report


def git_path():
    executable = shutil.which('git')
    if not executable:
        raise RuntimeError('缺少Git。请先安装官方Git/发行版Git；本包不自动安装系统工具。')
    path = Path(executable).resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or not os.access(path, os.X_OK):
        raise RuntimeError('Git路径不满足现有产品的可信可执行文件要求：'+str(path))
    return path


def check():
    require_platform()
    executable, override = _runtime_python_selection()
    dependencies = dependency_report(executable)
    if override and not dependencies['ready']:
        raise RuntimeError('OPENGUARD_PYTHON 未满足 CPython 3.12 及固定依赖要求。')
    report = {'platform':platform.platform(),'python':str(executable),'dependencies':dependencies,
              'git':str(git_path()),'samples':sample_report(),'frontend_present':(ROOT/'web/index.html').is_file(),
              'model_required_for_scan':False,'model_check':'NOT_REQUESTED','storage':'fresh package runtime/ only',
              'public_acquisition':'DISABLED','automatic_qwen':'DISABLED'}
    report['ready'] = (report['dependencies']['ready'] and report['frontend_present']
                       and all(x['match'] for x in report['samples']))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['ready'] else 2


def setup(offline_wheelhouse=None):
    require_platform()
    private_dir(RUNTIME)
    for name in ('tmp','cache'):
        private_dir(RUNTIME/name)
    target = RUNTIME/'venv'
    if target.exists():
        if not (target/'pyvenv.cfg').is_file():
            raise RuntimeError('runtime/venv已存在且不是可识别虚拟环境；不覆盖。')
    else:
        venv.EnvBuilder(with_pip=True,symlinks=True).create(target)
    python = target/'bin/python'
    version=subprocess.run([str(python),'-c','import sys;print(".".join(map(str,sys.version_info[:2])))'],
                           capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    if version!='3.12':raise RuntimeError('runtime/venv不是Python3.12，拒绝改装已有环境。')
    command = [str(python),'-m','pip','--disable-pip-version-check','install','--only-binary=:all:',
               '--retries','0','--timeout','30','--report',str(RUNTIME/'install-report.json'),
               '-r',str(ROOT/'deployment/requirements.lock')]
    if offline_wheelhouse:
        wh = Path(offline_wheelhouse).expanduser().resolve(strict=True)
        if not wh.is_dir():raise RuntimeError('wheelhouse必须为目录')
        command += ['--no-index','--find-links',str(wh)]
    else:
        command += ['--index-url','https://pypi.org/simple']
    install_env={k:v for k,v in os.environ.items() if not k.startswith('PIP_')}
    install_env.update({'PIP_CONFIG_FILE':os.devnull,'PIP_CACHE_DIR':str(RUNTIME/'cache/pip'),
                        'TMPDIR':str(RUNTIME/'tmp'),'PYTHONDONTWRITEBYTECODE':'1'})
    subprocess.run(command,check=True,cwd=ROOT,env=install_env)
    # Fixed source input is immutable at scan time; bytes have already been checked.
    if not all(x['match'] for x in sample_report()):raise RuntimeError('固定样例Hash不匹配')
    (ROOT/'samples/http-server.bundle').chmod(0o444)
    return check()


def parse_origin(origin):
    settings = deployment_settings()
    if origin == LOCAL_MODEL_ORIGIN or (settings.ollama_docker_host and origin == DOCKER_MODEL_ORIGIN):
        return urlsplit(origin)
    raise RuntimeError('模型地址只允许固定回环端点，或在双开关开启时显式指定 Docker 宿主机端点。')


def use_package_backend():
    sys.path.insert(0, str(APPLICATION / 'backend'))
    import app
    if not Path(app.__file__).resolve().is_relative_to(APPLICATION / 'backend'):
        raise RuntimeError('app模块来自包外源码，拒绝混用。')


def model_check(origin):
    value=parse_origin(origin)
    def get(path,limit):
        connection=http.client.HTTPConnection(value.hostname,value.port,timeout=5)
        try:
            connection.request('GET',path,headers={'Accept':'application/json'})
            response=connection.getresponse()
            if response.status!=200 or response.getheader('Location'):
                raise RuntimeError('本机模型身份GET失败：'+str(response.status))
            raw=response.read(limit+1)
            if len(raw)>limit:raise RuntimeError('模型身份响应超出上限')
            return json.loads(raw)
        finally:connection.close()
    if origin == DOCKER_MODEL_ORIGIN:
        use_package_backend()
        from app.ai import OllamaProvider
        provider = OllamaProvider(origin, docker_host=True)
        install_network_guard(origin)
        deadline = time.monotonic() + 5
        version = provider._request_json('/api/version', deadline=deadline, limit=4096)
        tags = provider._request_json('/api/tags', deadline=deadline, limit=262144)
    else:
        version=get('/api/version',4096);tags=get('/api/tags',262144)
    selected=[x for x in tags.get('models',[]) if isinstance(x,dict) and x.get('name')==MODEL_NAME]
    matches=(version.get('version')==OLLAMA_VERSION and len(selected)==1 and selected[0].get('digest')==MODEL_MANIFEST)
    report={'origin':origin,'ollama_expected':OLLAMA_VERSION,'ollama_actual':version.get('version'),
            'model':MODEL_NAME,'manifest_expected':MODEL_MANIFEST,'observed':selected,
            'weight_sha256_reference':MODEL_WEIGHT,'ready':matches,'generation_requests':0,
            'note':'只查询本机版本/标签，不下载、不生成、不启停模型；权重Hash是固定身份参考，本命令不读取模型权重。'}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if matches else 2


def configure_runtime(model_origin):
    parse_origin(model_origin)
    settings = deployment_settings()
    docker_model = model_origin == DOCKER_MODEL_ORIGIN
    private_dir(RUNTIME)
    for name in ('tmp','cache','account-data'):
        private_dir(RUNTIME/name)
    # Do not inherit feature gates or fixed object IDs from a caller's old demo.
    for key in list(os.environ):
        if key.startswith('OPENGUARD_'):
            os.environ.pop(key,None)
    for key in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):
        os.environ.pop(key,None)
    os.environ.update({
        'TMPDIR':str(RUNTIME/'tmp'),'XDG_CACHE_HOME':str(RUNTIME/'cache'),'PYTHONDONTWRITEBYTECODE':'1',
        'OPENGUARD_CONTAINER_MODE':'1' if settings.container_mode else '0',
        'OPENGUARD_ENABLE_AI':'0','OPENGUARD_OLLAMA_DOCKER_HOST':'1' if docker_model else '0',
        'OPENGUARD_ENABLE_PROFILE_METADATA':'0','OPENGUARD_ENABLE_EXTERNAL_SCANNERS':'0',
        'OPENGUARD_ENABLE_DURABLE_ZIP':'0','OPENGUARD_ENABLE_PROGRESS_EVENTS':'1',
        'OPENGUARD_ENABLE_ASSESSMENTS':'1','OPENGUARD_ENABLE_PUBLIC_GIT':'1',
        'OPENGUARD_ENABLE_REPORT_V2_1_1_WRITES':'1',
        'OPENGUARD_ENABLE_P2':'1','OPENGUARD_P2_READONLY':'0','OPENGUARD_P2_DATA_SCOPE':'TEST_ONLY',
        'OPENGUARD_ENABLE_ASSISTANT':'1','OPENGUARD_ASSISTANT_ORIGIN':model_origin,
        'OPENGUARD_ASSISTANT_LOCK_PATH':str(RUNTIME/'assistant-model.lock'),
        'OPENGUARD_ENABLE_P2_CHAT':'0','OPENGUARD_ENABLE_P2_AI':'1',
        'OPENGUARD_P2_AI_USAGE_MODE':'continuous','OPENGUARD_P2_AI_INPUT_SCOPE':'bound_materials',
        'OPENGUARD_P2_AI_BUDGET_PATH':str(RUNTIME/'p2-ai-continuous.json'),
        'OPENGUARD_P2_ACTION_PLAN':'0',
        'OPENGUARD_P2_AI_V4_PLAN':'1',
        'OPENGUARD_P2_PUBLIC_SOURCE_ROOT':str(APPLICATION/'tests/fixtures/task33/is-number-7.0.0'),
        'OPENGUARD_P2_PUBLIC_SOURCE_PROFILE_SHA256':'1a097309a5f9f5e9a5e50bdf6e6f0cced30449753e41108f8dfd207c36dfb308',
        'OPENGUARD_OFFICIAL_SOURCE_AUTO':'0','OPENGUARD_OFFICIAL_JOBS_ENABLED':'0',
    })
    samples=sample_report()
    if not all(x['match'] for x in samples):raise RuntimeError('固定样例完整性检查失败')
    sample = ROOT / 'samples/http-server.bundle'
    if stat.S_IMODE(sample.stat().st_mode) != 0o444:
        sample.chmod(0o444)


def install_network_guard(model_origin):
    """Application-level Python guard; deliberately not an OS sandbox claim."""
    target = parse_origin(model_origin)
    targets = {('127.0.0.1', target.port)}
    docker_dns = None
    if model_origin == DOCKER_MODEL_ORIGIN:
        docker_dns = (target.hostname, target.port)
        # The connection audit receives a numeric socket address. Pin local
        # answers at startup so later DNS changes cannot broaden egress.
        gateway_addresses = set()
        for family, kind, protocol, _, address in socket.getaddrinfo(
            *docker_dns, socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
        ):
            if (family, kind, protocol) != (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP):
                continue
            ip = ipaddress.IPv4Address(address[0])
            if (len(address) == 2 and address[1] == target.port
                    and (ip.is_loopback or any(ip in network for network in DOCKER_GATEWAY_NETWORKS))):
                gateway_addresses.add(address)
        if not gateway_addresses:
            raise RuntimeError('Docker 宿主机模型端点未解析为受支持的本地 IPv4 地址。')
        targets.update(gateway_addresses)

    def audit(event,args):
        if event=='socket.connect':
            address=args[1]
            if isinstance(address,tuple) and address in targets:return
            raise PermissionError('OpenGuard运行包只允许连接明确的本机Qwen地址，外部取证已关闭。')
        if event=='socket.getaddrinfo':
            host, port = args[:2]
            if docker_dns is not None and (host, port) == docker_dns:return
            try:allowed=host is None or ipaddress.ip_address(host).is_loopback
            except (ValueError,TypeError):allowed=host=='localhost'
            if not allowed:raise PermissionError('OpenGuard运行包禁止外部DNS。')
        if event in {'socket.gethostbyname', 'socket.gethostbyname_ex', 'socket.gethostbyaddr', 'socket.getnameinfo'}:
            raise PermissionError('OpenGuard运行包禁止未绑定模型端点的DNS查询。')
        if event == 'socket.sendto' or (event == 'socket.sendmsg' and args[1] is not None):
            raise PermissionError('OpenGuard运行包禁止向未连接的目标发送数据。')
    sys.addaudithook(audit)


def create_gateway(port,model_origin=LOCAL_MODEL_ORIGIN):
    """Composition entry for ASGI acceptance; no listener or model request here."""
    configure_runtime(model_origin)
    use_package_backend()
    from starlette.responses import Response,JSONResponse
    from app.api.main import create_default_app
    from app.ingestion.fixed_git_snapshot import FixedGitSnapshot
    from app.ingestion.git_stream import GitIngestionService
    from app.local_accounts import LocalAccountGateway
    profile=FixedGitSnapshot(bundle_path=ROOT/'samples/http-server.bundle',
        source_url='https://github.com/http-party/http-server',revision=REVISION,
        bundle_sha256=BUNDLE_SHA,bundle_size=462976,captured_at='2026-10-13T09:28:06.962574+00:00',
        capture_receipt_sha256='1b8cf6cdcb85778448b37eb838d395081a15bf378fe3a5ab37445d7d233d0045')
    dist=ROOT/'web'
    async def frontend(scope,receive,send):
        path=scope['path'].lstrip('/')
        if path=='healthz':
            return await JSONResponse({'status':'ok','data_scope':'TEST_ONLY','public_acquisition':'disabled',
                'automatic_qwen':'disabled','assistant':'explicit_local_only'})(scope,receive,send)
        target=(dist/path).resolve()
        if not target.is_relative_to(dist):return await Response(status_code=403)(scope,receive,send)
        if not path or path=='app' or path.startswith('app/') or path in {'login','register'}:
            target=dist/'index.html'
        if not target.is_file():return await Response(status_code=404)(scope,receive,send)
        headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-OpenGuard-Scope':'TEST_ONLY'}
        if target.name=='index.html':
            headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; media-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        return await Response(target.read_bytes(),media_type=mimetypes.guess_type(target.name)[0] or 'application/octet-stream',headers=headers)(scope,receive,send)
    origins=(f'http://127.0.0.1:{port}',f'http://localhost:{port}')
    os.environ['OPENGUARD_WEB_ORIGINS']=','.join(origins)
    return LocalAccountGateway(root=RUNTIME/'account-data',origins=origins,
        cookie_name='og_session_'+hashlib.sha256(str(ROOT).encode()).hexdigest()[:12],
        app_factory=lambda data:create_default_app(data_dir=data,
            git_ingestion_factory=lambda workspace:GitIngestionService(workspace,snapshot=profile,git_executable=git_path())),
        frontend=frontend)


def serve(port,model_origin,*,host='127.0.0.1'):
    require_platform()
    validate_listener(host)
    parse_origin(model_origin)
    settings = deployment_settings()
    if not dependency_report(Path(sys.executable))['ready']:
        raise RuntimeError('当前解释器依赖不匹配；先运行setup或check，不使用旧候选的私有依赖。')
    import fcntl
    configure_runtime(model_origin)
    fd=os.open(RUNTIME/'server.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            sock.bind((host,port));sock.listen(2048)
            actual=sock.getsockname()[1]
            app=create_gateway(actual,model_origin)
            import uvicorn
            install_network_guard(model_origin)
            info={'pid':os.getpid(),'url':f'http://127.0.0.1:{actual}/','host':host,'port':actual,
                  'started_utc':utc(),'data_dir':str(RUNTIME/'account-data'),'source':'this unpacked package',
                  'data_scope':'TEST_ONLY','public_acquisition':'DISABLED','automatic_qwen':'DISABLED',
                  'assistant':'explicit user requests only; local identity checks retained','old_accounts_imported':False}
            (RUNTIME/'SERVER.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
            print('READY '+info['url'],flush=True)
            print('首次使用请注册自己的账号。Ctrl+C只停止当前前台进程；runtime/保留。',flush=True)
            config = uvicorn.Config(app, host=host, port=actual, access_log=False, log_level='warning',
                                    timeout_graceful_shutdown=5 if settings.container_mode else None)
            # Uvicorn drains, restores the original handler, then re-raises
            # the signal. Translate that replay into the normal CLI exit path.
            original_term = signal.signal(signal.SIGTERM, signal.default_int_handler)
            try:
                uvicorn.Server(config).run(sockets=[sock])
            except KeyboardInterrupt:
                print('OpenGuard已停止，数据已保留。',flush=True)
            finally:
                signal.signal(signal.SIGTERM, original_term)


def build_frontend():
    require_platform()
    front=APPLICATION/'frontend'
    node=shutil.which('node')
    if not node:raise RuntimeError('重建前端需要已有Node；普通运行使用web/，不需要Node。')
    for rel in ['node_modules/typescript/bin/tsc','node_modules/vite/bin/vite.js']:
        if not (front/rel).is_file():raise RuntimeError('前端依赖缺失；先按锁文件pnpm install --frozen-lockfile。')
    env=dict(os.environ)
    env.update({'VITE_DATA_MODE':'api','VITE_API_BASE_URL':'/api/v1','VITE_P2_WORKBENCH':'1','VITE_ACCOUNT_AUTH':'1',
                'VITE_P2_AI_ANALYSIS':'1','VITE_OFFICIAL_SOURCE_AUTO':'0','VITE_REMEDIATION_READONLY':'1','VITE_PROGRESS_EVENTS':'1',
                'VITE_FIXED_GIT_SOURCE':'https://github.com/http-party/http-server','VITE_FIXED_GIT_REVISION':REVISION})
    subprocess.run([node,str(front/'node_modules/typescript/bin/tsc'),'--noEmit','-p',str(front/'tsconfig.json')],cwd=front,env=env,check=True)
    subprocess.run([node,str(front/'node_modules/vite/bin/vite.js'),'build','--outDir',str(ROOT/'web'),'--emptyOutDir'],cwd=front,env=env,check=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description='OpenGuard包内独立TEST_ONLY部署，不接入旧业务数据。')
    sub=parser.add_subparsers(dest='command',required=True)
    setup_parser=sub.add_parser('setup',help='创建包内私有venv并安装固定依赖')
    setup_parser.add_argument('--offline-wheelhouse')
    sub.add_parser('check',help='只读检查平台、精确依赖、样例和前端；不连接模型')
    model=sub.add_parser('model-check',help='只查询本机Ollama身份，不生成')
    model.add_argument('--origin',default=LOCAL_MODEL_ORIGIN)
    for command in ('start','serve'):
        start=sub.add_parser(command,help='前台启动；容器模式允许在容器内监听所有 IPv4 接口')
        start.add_argument('--port',type=int,default=0)
        start.add_argument('--host',default='127.0.0.1')
        start.add_argument('--model-origin',default=LOCAL_MODEL_ORIGIN)
    sub.add_parser('build',help='开发可选：用已有锁定前端依赖重建web/')
    sub.add_parser('self-test',help='新建隔离TEST_ONLY数据，实际验证扫描、用途、材料和导出；不调用模型')
    args=parser.parse_args(argv)
    try:
        deployment_settings()
        if args.command=='setup':return setup(args.offline_wheelhouse)
        if args.command=='check':return check()
        if args.command=='model-check':return model_check(args.origin)
        if args.command=='build':build_frontend();return 0
        if args.command=='self-test':
            require_platform()
            from deployment.selftest import main as selftest_main
            return selftest_main(ROOT, runtime_python())
        if not 0<=args.port<=65535:raise RuntimeError('端口必须在0–65535之间，0选择新空闲端口。')
        require_platform()
        validate_listener(args.host)
        parse_origin(args.model_origin)
        if args.command=='start':
            target=runtime_python()
            if Path(sys.executable).absolute()!=target.absolute():
                os.execv(str(target),[str(target),'-B',str(ROOT/'openguard.py'),'serve','--port',str(args.port),
                                       '--host',args.host,'--model-origin',args.model_origin])
        serve(args.port,args.model_origin,host=args.host)
        return 0
    except (RuntimeError,ValueError,OSError,http.client.HTTPException,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        print('ERROR: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
