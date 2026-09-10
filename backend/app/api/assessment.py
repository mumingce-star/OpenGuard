"""Additive V4 endpoints; all GETs read persisted sidecar state only."""
from __future__ import annotations
import hashlib
import sqlite3
from typing import Annotated, Literal
from urllib.parse import urlsplit
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel,ConfigDict,Field
from app.api.service import ApiError
from app.assessment.service import ERRORS
from app.assessment.store import AssessmentStoreError
from app.domain.usage import UsageDeclaration
from app.persistence.scan_registry import ScanRegistryError

class AssessmentRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:str=Field(min_length=1,max_length=200,pattern=r'^[A-Za-z0-9_.-]+$')
    usage:UsageDeclaration|None=None

class ChatRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    assessment_id:str=Field(min_length=1,max_length=200)
    request_id:str=Field(min_length=1,max_length=200,pattern=r'^[A-Za-z0-9_.-]+$')
    message:str=Field(min_length=1,max_length=2000)
    generation:int=Field(ge=0)

def failure(exc):
    code=getattr(exc,'code','assessment_storage_unavailable')
    missing=code in ('registry_not_found','registry_invalid_argument','assessment_not_found')
    status=404 if missing else 409 if any(s in code for s in ('conflict','not_ready')) else 422 if 'invalid' in code else 503
    message=ERRORS.get(code,'当前后端未启用本地 AI 答疑。' if code=='project_ai_disabled' else '评估或聊天状态无法处理；已有记录保留，请检查输入或稍后重试。')
    raise ApiError(status_code=status,code=code,message=message,reason=code)

def service(request:Request):return request.app.state.assessment_service

def router():
    r=APIRouter(prefix='/api/v1/scans/{scan_id}')

    def checked(scan_id,request):
        svc=service(request)
        try:svc.run(scan_id)
        except ScanRegistryError as e:failure(e)
        return svc

    @r.get('/assessments')
    def assessments(scan_id:str,request:Request,offset:int=Query(0,ge=0)):
        svc=checked(scan_id,request)
        try:
            items=svc.store.list(scan_id,limit=20,offset=offset)
            return {'items':items,'usage':svc.run(scan_id).project.usage,'offset':offset,'has_more':bool(svc.store.list(scan_id,limit=1,offset=offset+20)), 'pending_job': next((svc.job(scan_id,row[0]) for row in svc.store._read("SELECT request_id FROM assessment_jobs WHERE scan_id=? AND status='pending'",(scan_id,))),None)}
        except (AssessmentStoreError, sqlite3.Error, OSError) as e:failure(e)

    @r.post('/assessments',status_code=202)
    def create_assessment(scan_id:str,body:AssessmentRequest,request:Request,background_tasks:BackgroundTasks):
        svc=checked(scan_id,request)
        try:
            job,work=svc.reserve_assessment(scan_id,body.usage,body.request_id)
            if work:background_tasks.add_task(svc.generate_assessment,*work)
            return job
        except (AssessmentStoreError,ScanRegistryError,sqlite3.Error,OSError) as e:failure(e)

    @r.get('/assessments/jobs/{request_id}')
    def job(scan_id:str,request_id:str,request:Request):
        svc=checked(scan_id,request)
        result=svc.job(scan_id,request_id)
        if result is None:failure(AssessmentStoreError('assessment_not_found'))
        return result

    @r.get('/assessments/{assessment_id}')
    def assessment(scan_id:str,assessment_id:str,request:Request):
        svc=checked(scan_id,request)
        try:result=svc.store.get(scan_id,assessment_id)
        except (AssessmentStoreError, sqlite3.Error, OSError) as e:failure(e)
        if result is None:failure(AssessmentStoreError('assessment_not_found'))
        return result

    @r.get('/assessments/{assessment_id}/report')
    def report(scan_id:str,assessment_id:str,request:Request,format:Literal['html','json']='html'):
        svc=checked(scan_id,request)
        try:data=svc.store.report(scan_id,assessment_id,format)
        except (AssessmentStoreError, sqlite3.Error, OSError) as e:failure(e)
        if data is None:failure(AssessmentStoreError('assessment_not_found'))
        digest=hashlib.sha256(data).hexdigest()
        return Response(data,media_type='text/html' if format=='html' else 'application/json',headers={
            'Content-Disposition':f'attachment; filename="openguard-assessment-{digest[:16]}.{format}"',
            'X-Content-SHA256':digest,'X-Content-Type-Options':'nosniff',
            'Cache-Control':'no-store', 'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"})

    @r.get('/chat')
    def chat(scan_id:str,request:Request):
        svc=checked(scan_id,request)
        try:return svc.chat.history(scan_id)
        except (AssessmentStoreError, sqlite3.Error, OSError) as e:failure(e)

    @r.post('/chat',status_code=202)
    def send(scan_id:str,body:ChatRequest,request:Request,background_tasks:BackgroundTasks):
        svc=checked(scan_id,request)
        try:
            turn,work=svc.reserve_chat(scan_id,body.assessment_id,body.request_id,body.message,body.generation)
            if work:background_tasks.add_task(svc.generate_chat,*work)
            return turn
        except (AssessmentStoreError,ScanRegistryError,sqlite3.Error,OSError) as e:failure(e)

    @r.delete('/chat')
    def clear(scan_id:str,request:Request,confirmed:bool=False,generation:int=Query(...,ge=0)):
        svc=checked(scan_id,request)
        if confirmed is not True:failure(AssessmentStoreError('chat_clear_confirmation_invalid'))
        try:return svc.chat.clear(scan_id,generation)
        except (AssessmentStoreError, sqlite3.Error, OSError) as e:failure(e)
    return r
