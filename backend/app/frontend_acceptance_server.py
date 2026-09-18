"""Explicit opt-in acceptance process; uses no production configuration."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'prepare', 'serve', 'audit', 'validate'])
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--code-version', default='unrecorded-local-source')
    parser.add_argument('--port', type=int, default=18011)
    parser.add_argument('--web-port', type=int, default=15174)
    parser.add_argument('--api-origin-port', type=int, default=18011)
    args = parser.parse_args()
    if any(not 1024 <= p <= 65535 or p in {8000, 8011, 8080, 5174}
           for p in (args.port, args.web_port, args.api_origin_port)):
        parser.error('isolated ports required')
    os.umask(0o077)
    from app import frontend_acceptance as seed
    if args.action != 'serve':
        if args.action == 'init':
            value = seed.initialize(args.root, code_version=args.code_version)
        elif args.action == 'prepare':
            value = seed.prepare(args.root)
        elif args.action == 'validate':
            value = seed.read_manifest(args.root)
        else:
            value = seed.logical_state(args.root)
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return
    import uvicorn
    origins = tuple(f'http://{h}:{p}' for h in ('127.0.0.1', 'localhost')
                    for p in (args.web_port, args.api_origin_port))
    os.environ['OPENGUARD_WEB_ORIGINS'] = ','.join(origins)
    app = seed.create_acceptance_app(args.root, origins=origins)
    uvicorn.run(app, host='0.0.0.0', port=args.port, workers=1, reload=False, access_log=False)


if __name__ == '__main__':
    main()
