"""A real loopback acceptance run, isolated from the user's normal account store."""
from pathlib import Path
import datetime, json, os, signal, subprocess, time, uuid


def main(root, python):
    root=Path(root)
    tests=root/'runtime'/'self-tests'
    tests.mkdir(parents=True,exist_ok=True,mode=0o700)
    run=tests/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    run.mkdir(mode=0o700)
    env=dict(os.environ)
    env.update(OPENGUARD_PACKAGE_SELFTEST_ROOT=str(run),PYTHONDONTWRITEBYTECODE='1')
    process=None
    result={'kind':'REAL_LOOPBACK_HTTP_TEST_ONLY','external_acquisition_requests':0,'model_generation_requests':0,'status':'FAIL'}
    try:
        with (run/'server.stdout').open('w') as out,(run/'server.stderr').open('w') as err:
            process=subprocess.Popen([str(python),'-B',str(root/'openguard.py'),'serve','--port','0'],cwd=root,env=env,stdout=out,stderr=err)
            deadline=time.monotonic()+45
            ready=run/'SERVER.json'
            while not ready.exists():
                if process.poll() is not None:raise RuntimeError('Test server exited; inspect server.stderr')
                if time.monotonic()>deadline:raise RuntimeError('Test server readiness timeout')
                time.sleep(.1)
            base=json.loads(ready.read_text())['url'].rstrip('/')
            with (run/'acceptance.stdout').open('w') as aout,(run/'acceptance.stderr').open('w') as aerr:
                completed=subprocess.run([str(python),'-B',str(root/'deployment/acceptance.py'),base,str(run/'http')],cwd=root,env=env,stdout=aout,stderr=aerr,timeout=240)
            result['acceptance_exit_code']=completed.returncode
            if completed.returncode==0:
                index=json.loads((run/'http/INDEX.json').read_text())
                result.update(status='PASS',checks=len(index['checks']),http_requests=len(index['requests']))
    except (OSError,RuntimeError,subprocess.TimeoutExpired,ValueError,KeyError) as exc:
        result['error']=str(exc)
    finally:
        if process and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        if process:result['test_server_exit_code']=process.returncode
        result['normal_account_store_untouched']=True
        result['evidence_directory']=str(run.relative_to(root))
        (run/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='PASS' else 2
