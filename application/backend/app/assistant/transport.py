"""Pinned loopback Ollama role chat with real NDJSON, cancellation and no retry."""
from __future__ import annotations
import fcntl
import http.client
import os
from pathlib import Path
import socket
import stat
import threading
import time
from urllib.parse import urlsplit
from app.ai.ollama import OllamaProvider, MODEL_NAME, MANIFEST_DIGEST, OLLAMA_VERSION, _MODEL_SLOT
from app.p2.contract import canonical, strict_json
from .store import AssistantError

class Cancellation:
    def __init__(self):
        self.reason=None;self._lock=threading.Lock();self._connection=None;self._socket=None;self._response=None
    def attach(self,connection):
        with self._lock:
            self._connection=connection
            if self.reason:connection.close();raise AssistantError('assistant_'+self.reason,409)
    def attach_response(self,connection,response,sock):
        with self._lock:
            self._response=response;self._socket=sock
        if self.reason:self.request(self.reason);self.check()
    def detach(self,connection):
        with self._lock:
            if self._connection is connection:self._connection=None;self._socket=None;self._response=None
    def request(self,reason='stopped'):
        with self._lock:
            if self.reason is None:self.reason=reason
            connection=self._connection;current_socket=self._socket or getattr(connection,"sock",None);response=self._response
        # HTTPConnection detaches sock on Connection:close. Keep the actual pre-response socket.
        if current_socket is not None:
            try:current_socket.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        if response is not None:
            try:response.close()
            except OSError:pass
        if connection is not None:connection.close()
    def check(self):
        if self.reason:raise AssistantError('assistant_'+self.reason,409 if self.reason=='stopped' else 504)

class ModelCoordinator:
    """Shares the legacy in-process slot, plus one TASK-wide interprocess lock."""
    def __init__(self,path):self.path=Path(path)
    def acquire(self):
        info=self.path.parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_mode&0o077 or info.st_uid!=os.geteuid():
            raise AssistantError('assistant_model_lock_invalid',503)
        if not _MODEL_SLOT.acquire(blocking=False):raise AssistantError('assistant_model_busy',409)
        fd=None
        try:
            fd=os.open(self.path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or info.st_nlink!=1 or info.st_uid!=os.geteuid():
                raise AssistantError('assistant_model_lock_invalid',503)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise AssistantError('assistant_model_busy',409) from None
            return fd
        except BaseException:
            if fd is not None:os.close(fd)
            _MODEL_SLOT.release();raise
    @staticmethod
    def release(fd):
        try:os.close(fd)
        finally:_MODEL_SLOT.release()

class StreamingQwen:
    def __init__(self,origin='http://127.0.0.1:11434',*,connection_factory=http.client.HTTPConnection):
        origin=OllamaProvider(origin)._origin # existing literal-loopback origin validation; never consult proxies.
        parsed=urlsplit(origin);self.host,self.port=parsed.hostname,parsed.port;self.factory=connection_factory
    def _request(self,path,control,deadline,*,body=None):
        control.check();remaining=deadline-time.monotonic()
        if remaining<=0:raise AssistantError('assistant_timeout',504)
        conn=self.factory(self.host,self.port,timeout=remaining)
        control.attach(conn)
        try:
            conn.request('POST' if body is not None else 'GET',path,
                         body=canonical(body) if body is not None else None,
                         headers={'Content-Type':'application/json','Accept':'application/x-ndjson' if body else 'application/json','Connection':'close'})
            active_socket=conn.sock
            response=conn.getresponse()
            control.attach_response(conn,response,active_socket)
            if response.status!=200:raise AssistantError('assistant_model_http_rejected',503)
            if response.getheader('Location') is not None:raise AssistantError('assistant_model_redirect_rejected',503)
            return conn,response
        except BaseException:
            conn.close();control.detach(conn);raise
    def _json(self,path,control,deadline,limit):
        conn,response=self._request(path,control,deadline)
        try:
            raw=response.read(limit+1);control.check()
            if len(raw)>limit:raise AssistantError('assistant_model_identity_invalid',503)
            return strict_json(raw)
        finally:conn.close();control.detach(conn)
    def generate(self,messages,control,emit,*,schema=None):
        deadline=time.monotonic()+120
        version=self._json('/api/version',control,deadline,4096)
        tags=self._json('/api/tags',control,deadline,262144)
        matches=[m for m in tags.get('models',[]) if isinstance(m,dict) and m.get('name')==MODEL_NAME]
        if version.get('version')!=OLLAMA_VERSION or len(matches)!=1 or matches[0].get('digest')!=MANIFEST_DIGEST:
            raise AssistantError('assistant_model_identity_mismatch',503)
        body={'model':MODEL_NAME,'messages':messages,'stream':True,'think':False,
              'options':{'temperature':0.3 if schema is None else 0,'num_predict':4096 if schema is None else 1800,'num_ctx':16384}}
        if schema is not None:body['format']=schema
        if len(canonical(body))>131072:raise AssistantError('assistant_model_input_limit',413)
        conn,response=self._request('/api/chat',control,deadline,body=body)
        total=0;characters=0
        try:
            while True:
                control.check()
                if time.monotonic()>=deadline:raise AssistantError('assistant_timeout',504)
                raw=response.readline(131073)
                if not raw:raise AssistantError('assistant_stream_incomplete',503)
                total+=len(raw)
                if len(raw)>131072 or total>1048576:raise AssistantError('assistant_model_wire_limit',413)
                if not raw.endswith(b'\n'):raise AssistantError('assistant_stream_framing_invalid',503)
                item=strict_json(raw)
                if not isinstance(item,dict) or item.get('model')!=MODEL_NAME or item.get('error'):
                    raise AssistantError('assistant_stream_identity_invalid',503)
                message=item.get('message')
                if not isinstance(message,dict) or message.get('role')!='assistant' or not isinstance(message.get('content'),str):
                    raise AssistantError('assistant_stream_message_invalid',503)
                if message.get('tool_calls'):raise AssistantError('assistant_tools_not_enabled',503)
                text=message['content'];characters+=len(text)
                if characters>24000:raise AssistantError('assistant_output_limit',413)
                if text:emit(text)
                if item.get('done') is True:
                    if item.get('done_reason') not in (None,'stop'):raise AssistantError('assistant_output_truncated',503)
                    if not characters:raise AssistantError('assistant_empty_output',503)
                    return {k:item[k] for k in ('done','done_reason','total_duration','prompt_eval_count','eval_count') if k in item}
                if item.get('done') is not False:raise AssistantError('assistant_stream_framing_invalid',503)
        finally:conn.close();control.detach(conn)
