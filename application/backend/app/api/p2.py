"""Normal P2 HTTP contract; explicit synchronous writes and immutable reads."""
from __future__ import annotations

from uuid import uuid4
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.p2.contract import (Answer, AnswerRequest, Binding, CreateRequest, Material,
                             MaterialRequest, P2Error, Receipt, Result, ResultIndex, Summary, ErrorEnvelope)
from app.p2.preliminary import PreliminaryAdvice
from app.p2.material_claims_contract import MaterialClaims
from app.p2.automatic_contract import AutomaticReview
from app.p2.ai_analysis import AnalysisRequest
from app.p2.project_chat import ChatRequest
from app.p2.official_sources import AdoptRequest, ExplicitFetchRequest, ExplicitAnalysisRequest

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
            value = getattr(svc, name)(*args)
            # Formal save has committed; optional analysis cannot turn it into a failed save.
            if name == 'write' and getattr(svc, 'official_sources', None) is not None:
                svc.official_sources.safe_on_result(args[0], args[1], value)
            return value
        except P2Error as exc:
            return error_response(request, exc)
        except ValidationError:
            return error_response(request, P2Error('p2_integrity_error', 503))

    def ai_call(request, name, *args):
        parent = getattr(request.app.state, 'p2_service', None)
        svc = getattr(parent, 'ai_analysis', None)
        if svc is None:
            return error_response(request, P2Error('p2_ai_disabled', 503))
        try:
            return getattr(svc, name)(*args)
        except P2Error as exc:
            return error_response(request, exc)
        except ValidationError:
            return error_response(request, P2Error('p2_ai_integrity_error', 503))

    def official_call(request, name, *args):
        parent = getattr(request.app.state, 'p2_service', None)
        svc = getattr(parent, 'official_sources', None)
        if svc is None:
            return error_response(request, P2Error('official_sources_disabled', 503))
        try:
            return getattr(svc, name)(*args)
        except P2Error as exc:
            return error_response(request, exc)
        except ValidationError:
            return error_response(request, P2Error('official_source_integrity_error', 503))

    def chat_call(request, name, *args):
        parent = getattr(request.app.state, 'p2_service', None)
        svc = getattr(parent, 'project_chat', None)
        if svc is None:
            return error_response(request, P2Error('p2_chat_disabled', 503))
        try:
            return getattr(svc, name)(*args)
        except P2Error as exc:
            return error_response(request, exc)
        except ValidationError:
            return error_response(request, P2Error('p2_chat_integrity_error', 503))

    @r.get('/project-chat')
    def project_chat(scan_id: str, assessment_id: str, request: Request,
                     result_id: str, assessment_version: int = Query(ge=1)):
        return chat_call(request, 'snapshot', scan_id, assessment_id, assessment_version, result_id)

    @r.post('/project-chat', status_code=201)
    def project_chat_send(scan_id: str, assessment_id: str, body: ChatRequest, request: Request):
        return chat_call(request, 'send', scan_id, assessment_id, body)

    @r.get('/official-sources')
    def official_status(scan_id: str, assessment_id: str, request: Request,
                        result_id: str, assessment_version: int = Query(ge=1)):
        return official_call(request, 'status', scan_id, assessment_id, assessment_version, result_id)

    @r.post('/official-sources/fetch', status_code=202)
    def official_fetch(scan_id: str, assessment_id: str, body: ExplicitFetchRequest, request: Request):
        return official_call(request, 'request_fetch', scan_id, assessment_id, body)

    @r.post('/official-sources/analyze', status_code=202)
    def official_analyze(scan_id: str, assessment_id: str, body: ExplicitAnalysisRequest, request: Request):
        return official_call(request, 'request_analysis', scan_id, assessment_id, body)

    @r.post('/official-sources/adopt', status_code=201, response_model=Receipt)
    def official_adopt(scan_id: str, assessment_id: str, body: AdoptRequest, request: Request):
        return official_call(request, 'adopt', scan_id, assessment_id, body)

    @r.post('/ai-analyses', status_code=201)
    def ai_create(scan_id: str, assessment_id: str, body: AnalysisRequest, request: Request):
        parent = getattr(request.app.state, 'p2_service', None)
        if getattr(parent, 'official_sources', None) is not None:
            return error_response(request, P2Error('p2_ai_automatically_managed', 403))
        return ai_call(request, 'create', scan_id, assessment_id, body)

    @r.get('/ai-analyses')
    def ai_index(scan_id: str, assessment_id: str, request: Request, result_id: str, assessment_version: int = Query(ge=1)):
        return ai_call(request, 'index', scan_id, assessment_id, result_id, assessment_version)

    @r.get('/ai-analyses/{analysis_id}')
    def ai_read(scan_id: str, assessment_id: str, analysis_id: str, request: Request, result_id: str, assessment_version: int = Query(ge=1)):
        return ai_call(request, 'read', scan_id, assessment_id, analysis_id, result_id, assessment_version)

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

    @r.get('/results/{result_id}/preliminary-advice', response_model=PreliminaryAdvice)
    def preliminary(scan_id: str, assessment_id: str, result_id: str, request: Request, assessment_version: int = Query(ge=1)):
        return call(request, 'preliminary_advice', scan_id, assessment_id, result_id, assessment_version)

    @r.get('/results/{result_id}/material-claims', response_model=MaterialClaims)
    def material_claims(scan_id: str, assessment_id: str, result_id: str, request: Request, assessment_version: int = Query(ge=1)):
        return call(request, 'material_claims', scan_id, assessment_id, result_id, assessment_version)

    @r.get('/results/{result_id}/automatic-review', response_model=AutomaticReview)
    def automatic_review(scan_id: str, assessment_id: str, result_id: str, request: Request, assessment_version: int = Query(ge=1)):
        return call(request, 'automatic_review', scan_id, assessment_id, result_id, assessment_version)

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
