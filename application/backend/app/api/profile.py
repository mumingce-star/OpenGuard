"""Profile HTTP adapter: reads never fetch, refresh explicitly opted in."""
from fastapi import APIRouter, Request
from app.api.models import ErrorEnvelope
from app.api.service import ApiError
from app.p1.profile_models import ResourceProfile, RefreshRequest, RefreshJob
from app.p1.profile_store import ProfileError


def router():
    r=APIRouter(prefix='/api/v1/scans/{scan_id}',tags=['ResourceProfile'])
    errors={s:{'model':ErrorEnvelope} for s in (400,403,404,409,413,422,503)}
    def execute(request,method,*args):
        if request.query_params:
            raise ApiError(status_code=400,code='invalid_argument',message='Profile request invalid.',reason='request_invalid')
        try: return getattr(request.app.state.profile_service,method)(*args)
        except ProfileError as error:
            status={'not_found':404,'conflict':409,'not_ready':409,'not_comparable':409,
                    'invalid_argument':400,'metadata_invalid':422}.get(error.code,503)
            raise ApiError(status_code=status,code=error.code,message='Profile request could not be completed.',reason=error.code) from None
    @r.get('/resources/{resource_id}/profile',response_model=ResourceProfile,responses=errors)
    def get(scan_id:str,resource_id:str,request:Request): return execute(request,'get',scan_id,resource_id)
    @r.post('/resource-profiles/refresh',response_model=RefreshJob,responses=errors)
    def refresh(scan_id:str,body:RefreshRequest,request:Request): return execute(request,'refresh',scan_id,body)
    @r.get('/resource-profiles/jobs/{job_id}',response_model=RefreshJob,responses=errors)
    def job(scan_id:str,job_id:str,request:Request): return execute(request,'job',scan_id,job_id)
    return r
