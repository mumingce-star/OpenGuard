"""Private account assistant API. POST reserves once; GET only replays persisted events."""
from __future__ import annotations
import asyncio
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field
from app.p2.contract import DTO, ID, SHA, P2Error, canonical
from app.assistant.store import AssistantError, VERSION

class ProjectRef(DTO):
    scan_id:ID
    assessment_id:ID
    assessment_version:int=Field(ge=1)
    result_id:ID
    result_sha256:SHA
class ConversationRequest(DTO):
    request_id:str=Field(min_length=8,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    context:ProjectRef|None=None
class MessageRequest(DTO):
    request_id:str=Field(min_length=8,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    message:str=Field(min_length=1,max_length=8000)
class StopRequest(DTO):pass

def error(exc):
    code=getattr(exc,'code','assistant_unavailable');status=getattr(exc,'status',503)
    return JSONResponse(status_code=status,content={'error':{'code':code,'message':{
        'assistant_rate_limited':'发送过快，请稍后继续；没有对话总次数限制。',
        'assistant_model_busy':'模型正在处理另一个请求，请稍后主动发送。',
        'assistant_idempotency_conflict':'同一请求身份不能用于不同内容。',
    }.get(code,'本次操作未完成，已保存对话保留；不会自动重复生成。')}},headers={'Cache-Control':'no-store'})

def router():
    r=APIRouter(prefix='/api/v1/assistant',tags=['TASK account assistant'])
    def service(request):
        value=getattr(request.app.state,'assistant_service',None)
        if value is None:raise AssistantError('assistant_disabled',503)
        return value
    def invoke(request,name,*args):
        try:return getattr(service(request),name)(*args)
        except (AssistantError,P2Error) as exc:return error(exc)
    @r.get('/conversations')
    def conversations(request:Request,cursor:int|None=Query(default=None,ge=1),limit:int=Query(default=100,ge=1,le=100)):
        try:return service(request).store.conversations(cursor,limit)
        except (AssistantError,P2Error) as exc:return error(exc)
    @r.post('/conversations',status_code=201)
    def create(body:ConversationRequest,request:Request):
        return invoke(request,'create',body.request_id,None if body.context is None else body.context.model_dump())
    @r.get('/conversations/{cid}')
    def detail(cid:str,request:Request,cursor:int|None=Query(default=None,ge=1),limit:int=Query(default=100,ge=1,le=100)):
        return invoke(request,'detail',cid,cursor,limit)
    @r.post('/conversations/{cid}/messages',status_code=202)
    def message(cid:str,body:MessageRequest,request:Request):return invoke(request,'send',cid,body.request_id,body.message)
    @r.get('/conversations/{cid}/messages/{request_id}/events')
    async def events(cid:str,request_id:str,request:Request,after:int=Query(default=0,ge=0)):
        try:
            svc=service(request);svc.store.events(cid,request_id,after) # status before streaming headers.
        except (AssistantError,P2Error) as exc:return error(exc)
        async def stream():
            seq=after
            while True:
                items,terminal=svc.store.events(cid,request_id,seq)
                for item in items:
                    seq=item['seq'];yield canonical(item)+b'\n'
                if terminal:break
                if await request.is_disconnected():break
                await asyncio.sleep(.08)
        return StreamingResponse(stream(),media_type='application/x-ndjson',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
    @r.post('/conversations/{cid}/messages/{request_id}/stop')
    def stop(cid:str,request_id:str,body:StopRequest,request:Request):return invoke(request,'stop',cid,request_id)
    return r
