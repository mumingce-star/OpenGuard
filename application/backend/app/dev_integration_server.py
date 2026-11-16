"""Explicit process entrypoint used only by deploy/p1_dev.py."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'serve'])
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--code-version', default='unrecorded-local-source')
    parser.add_argument('--port', type=int, default=18011)
    parser.add_argument('--web-port', type=int, default=15174)
    parser.add_argument('--api-origin-port', type=int, default=18011)
    args = parser.parse_args(argv)
    if any(not 1024 <= port <= 65535 or port in {8000, 8011, 8080, 5174}
           for port in (args.port, args.web_port, args.api_origin_port)):
        parser.error('only unprivileged isolated ports are allowed')
    os.umask(0o077)
    from app.dev_integration import initialize, create_dev_app
    if args.action == 'init':
        manifest = initialize(args.root, code_version=args.code_version)
        print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))
        return
    import uvicorn
    origins = tuple(f'http://{host}:{port}' for host in ('127.0.0.1', 'localhost')
                    for port in (args.web_port, args.api_origin_port))
    os.environ["OPENGUARD_WEB_ORIGINS"] = ",".join(origins)
    app = create_dev_app(args.root, origins=origins)
    # Docker publishes this single port only on host loopback. No reload/worker pool.
    uvicorn.run(app, host='0.0.0.0', port=args.port, workers=1, reload=False, access_log=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Isolated development failed: ' + getattr(error, 'code', type(error).__name__), file=sys.stderr)
        raise SystemExit(1)
