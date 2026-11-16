"""NoticeDraft API: injected immutable service, unavailable by default."""
from fastapi import APIRouter, Request
from app.api.models import ErrorEnvelope
from app.api.service import ApiError
from app.p1.models import P1NoticeDraft, P1Model
from app.p1.notice_draft import NoticeDraftServiceError
from pydantic import Field, model_validator
from typing import Annotated

PREFIX = '/api/v1/scans/{scan_id}/assessments/{assessment_id}/notice-drafts'


class NoticeDraftCreateRequest(P1Model):
    idempotency_key: Annotated[str, Field(strict=True, min_length=1, max_length=200)]

    @model_validator(mode='after')
    def nonblank(self):
        if not self.idempotency_key.strip():
            raise ValueError('idempotency_key_invalid')
        return self


def fail(code, reason):
    status = {'invalid_argument': 400, 'not_found': 404, 'conflict': 409,
              'not_ready': 409, 'not_comparable': 409, 'feature_disabled': 503}.get(code, 503)
    raise ApiError(status_code=status, code=code, reason=reason, message='Notice draft request could not be completed.')


def service(request, *, reading=False):
    if request.query_params:
        fail('invalid_argument', 'request_invalid')
    value = request.app.state.notice_draft_service
    if value is None:
        if reading:
            # No Notice store is configured, hence there is no saved draft.
            # Keep legacy Acceptance /1 and /2 unavailable GET semantics while
            # exposing the formal route and its response contract in OpenAPI.
            fail('not_found', 'notice_not_found')
        fail('feature_disabled', 'notice_not_configured')
    return value


def router():
    result = APIRouter(prefix=PREFIX, tags=['NoticeDraft'])
    errors = {code: {'model': ErrorEnvelope} for code in (400, 403, 404, 409, 413, 503)}

    @result.post('', response_model=P1NoticeDraft, responses=errors)
    def create(scan_id: str, assessment_id: str, payload: NoticeDraftCreateRequest, request: Request):
        try:
            return service(request).create(scan_id, assessment_id, idempotency_key=payload.idempotency_key)
        except NoticeDraftServiceError as error:
            fail(error.code, error.reason)

    @result.get('/{draft_id}', response_model=P1NoticeDraft, responses=errors)
    def get(scan_id: str, assessment_id: str, draft_id: str, request: Request):
        try:
            saved = service(request, reading=True).get(scan_id, assessment_id, draft_id)
        except NoticeDraftServiceError as error:
            fail(error.code, error.reason)
        if saved is None:
            fail('not_found', 'notice_not_found')
        return saved

    return result
