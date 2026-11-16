"""TASK candidate: authenticated tenant routing supplies read-only dependencies."""
from base64 import b64encode
import hashlib

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import ValidationError

from app.api.p2 import PREFIX, error_response
from app.p2.contract import ErrorEnvelope, P2Error
from app.p2.evaluation_export import build_package


def router():
    r = APIRouter(prefix=PREFIX, tags=['Read-only evaluation package'])

    @r.get('/results/{result_id}/evaluation-package', responses={409: {'model': ErrorEnvelope}})
    def download(scan_id: str, assessment_id: str, result_id: str, request: Request,
                 assessment_version: int = Query(ge=1), report_snapshot_id: str | None = None,
                 analysis_id: str | None = None, preview_id: str | None = None):
        allowed = {'assessment_version', 'report_snapshot_id', 'analysis_id', 'preview_id'}
        if (set(request.query_params) - allowed
                or any(len(request.query_params.getlist(k)) != 1 for k in request.query_params)):
            return error_response(request, P2Error('evaluation_package_selection_invalid', 422))
        p2 = getattr(request.app.state, 'p2_service', None)
        if p2 is None:
            return error_response(request, P2Error('p2_service_disabled', 503))
        try:
            raw, result = build_package(p2, getattr(request.app.state, 'assessment_service', None),
                getattr(request.app.state, 'report_v2_service', None), scan_id, assessment_id,
                result_id, assessment_version, report_snapshot_id=report_snapshot_id,
                analysis_id=analysis_id, preview_id=preview_id)
        except P2Error as exc:
            return error_response(request, exc)
        except (ValidationError, ValueError, KeyError, TypeError):
            return error_response(request, P2Error('evaluation_package_source_integrity_error', 503))
        except Exception:
            # Never leak a storage path, raw SQL, or an unredacted source error.
            return error_response(request, P2Error('evaluation_package_unavailable', 503))
        sha = hashlib.sha256(raw).hexdigest()
        return Response(raw, media_type='application/zip', headers={
            'Content-Disposition': f'attachment; filename="OpenGuard-evaluation-{sha}.zip"',
            'Content-Digest': 'sha-256=:' + b64encode(bytes.fromhex(sha)).decode() + ':',
            'ETag': f'"sha256:{sha}"', 'X-Content-SHA256': sha,
            'X-OpenGuard-Result-ID': result['result_id'],
            'X-OpenGuard-Result-SHA256': result['result_sha256'],
            'X-OpenGuard-Result-Revision': str(result['revision']),
            'X-OpenGuard-Assessment-Version': str(assessment_version),
            'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
        })

    return r
