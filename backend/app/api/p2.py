"""Normal P2 HTTP contract; explicit synchronous writes and immutable reads."""
from __future__ import annotations

from uuid import uuid4
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.p2.contract import (Answer, AnswerRequest, Binding, CreateRequest, Material,
                             MaterialRequest, P2Error, Receipt, Result, ResultIndex, Summary, ErrorEnvelope)

PREFIX = '/api/v1/scans/{scan_id}/assessments/{assessment_id}/p2'


def error_response(request, error):
    request_id = getattr(request.state, 'request_id', 'req_' + str(uuid4()))
    state = 'conflict' if error.status == 409 else 'unavailable' if error.status == 503 else 'rejected'
    return JSONResponse(status_code=error.status, content={'error': {
        'code': error.code, 'message': '操作未完成；已保存结果保留。请按精确身份重新读取。',
        'request_id': request_id, 'details': {'reason': error.code, 'state': state,
        'retry': 'READ_EXACT_THEN_REUSE_SAME_KEY_AND_BODY', **error.details}}},
        headers={'X-Request-ID': request_id, 'Cache-Control': 'no-store'})


def router():
    r = APIRouter(prefix=PREFIX, tags=['P2 non-Formal results'],
                  responses={code: {'model': ErrorEnvelope} for code in (403, 404, 409, 413, 422, 503)})

    def call(request, name, *args):
        svc = getattr(request.app.state, 'p2_service', None)
        if svc is None:
            return error_response(request, P2Error('p2_service_disabled', 503))
        try:
            return getattr(svc, name)(*args)
        except P2Error as exc:
            return error_response(request, exc)
        except ValidationError:
            return error_response(request, P2Error('p2_integrity_error', 503))

    @r.get('/binding', response_model=Binding)
    def binding(scan_id: str, assessment_id: str, request: Request):
        result = call(request, 'context', scan_id, assessment_id)
        return result if isinstance(result, JSONResponse) else result[2]

    @r.get('/results', response_model=ResultIndex)
    def index(scan_id: str, assessment_id: str, request: Request, assessment_version: int = Query(ge=1), offset: int = Query(0, ge=0, le=10000)):
        return call(request, 'index', scan_id, assessment_id, assessment_version, offset)

    @r.post('/results', status_code=201, response_model=Receipt)
    def create(scan_id: str, assessment_id: str, body: CreateRequest, request: Request):
        return call(request, 'write', scan_id, assessment_id, body, 'create')

    @r.get('/results/{result_id}', response_model=Result)
    def read(scan_id: str, assessment_id: str, result_id: str, request: Request, assessment_version: int = Query(ge=1)):
        return call(request, 'read', scan_id, assessment_id, result_id, assessment_version)

    @r.get('/results/{result_id}/summary', response_model=Summary)
    def summary(scan_id: str, assessment_id: str, result_id: str, request: Request, assessment_version: int = Query(ge=1)):
        return call(request, 'summary', scan_id, assessment_id, result_id, assessment_version)

    @r.post('/answers', status_code=201, response_model=Receipt)
    def answer(scan_id: str, assessment_id: str, body: AnswerRequest, request: Request):
        return call(request, 'write', scan_id, assessment_id, body, 'answer')

    @r.get('/answers/{answer_id}', response_model=Answer)
    def read_answer(scan_id: str, assessment_id: str, answer_id: str, request: Request, assessment_version: int = Query(ge=1)):
        return call(request, 'record', scan_id, assessment_id, 'answer', answer_id, assessment_version)

    @r.post('/materials', status_code=201, response_model=Receipt)
    def material(scan_id: str, assessment_id: str, body: MaterialRequest, request: Request):
        return call(request, 'write', scan_id, assessment_id, body, 'material')

    @r.get('/materials/{material_id}', response_model=Material)
    def read_material(scan_id: str, assessment_id: str, material_id: str, request: Request, assessment_version: int = Query(ge=1)):
        return call(request, 'record', scan_id, assessment_id, 'material', material_id, assessment_version)

    return r
