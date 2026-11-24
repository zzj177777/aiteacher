"""Session-authorized planner input/output traces, independent of classroom commits."""
import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

LIMIT=30
MAX_TEXT=700000
_scope=ContextVar('model_debug_scope',default={})
_call=ContextVar('model_debug_call',default=None)
_private={'authorization','api_key','access_token','token','token_hash','rubric','private_rubric',
          'reasoning_content','reasoning','chain_of_thought'}


@contextmanager
def scope(**values):
    token=_scope.set({**_scope.get(),**values})
    try:yield
    finally:_scope.reset(token)


def path():
    root=Path(__file__).resolve().parents[1]
    classroom=Path(os.getenv('AITEACHER_DB',str(root/'data'/'classroom.sqlite3')))
    return Path(os.getenv('AITEACHER_MODEL_DEBUG_DB',str(classroom.parent/'model_debug.sqlite3')))


def connect():
    target=path();target.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(target,timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS planner_traces(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,started_at TEXT NOT NULL,record TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS planner_traces_session ON planner_traces(session_id,started_at)')
    return db


def safe(value):
    """Keep raw argument strings unless private fields require redaction."""
    if isinstance(value,dict):return {k:('[已隐藏]' if k.lower() in _private else safe(v)) for k,v in value.items()}
    if isinstance(value,list):return [safe(item) for item in value]
    if isinstance(value,str):
        secret=os.getenv('AI_API_KEY','')
        if len(secret)>=8:value=value.replace(secret,'[已隐藏密钥]')
        if value.lstrip().startswith(('{','[')):
            try:
                decoded=json.loads(value);clean=safe(decoded)
                if clean!=decoded:value=json.dumps(clean,ensure_ascii=False)
            except (ValueError,RecursionError):pass
        return value[:MAX_TEXT]+'\n[内容过长，已截断]' if len(value)>MAX_TEXT else value
    return value


def save(record):
    try:
        db=connect()
        try:
            with db:
                db.execute('INSERT INTO planner_traces VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET record=excluded.record',
                           (record['id'],record['session_id'],record['at'],json.dumps(record,ensure_ascii=False)))
                db.execute('DELETE FROM planner_traces WHERE session_id=? AND id NOT IN (SELECT id FROM planner_traces WHERE session_id=? ORDER BY started_at DESC,id DESC LIMIT ?)',
                           (record['session_id'],record['session_id'],LIMIT))
        finally:db.close()
    except Exception:
        # Diagnostics must never break teaching or leak input/output into server logs.
        logging.getLogger(__name__).error('planner_debug_write_failed call_id=%s',record['id'])


def capture_request(body):
    record=_call.get()
    if record is None:return
    record.update(request=safe(body),status='pending',sent_at=datetime.now(timezone.utc).isoformat())
    save(record)


def capture_response(body):
    record=_call.get()
    if record is None:return
    record.update(response=safe(body),received_at=datetime.now(timezone.utc).isoformat())
    save(record)


def planner_call(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        context=_scope.get()
        if not context.get('session_id'):return function(*args,**kwargs)
        record=dict(id=str(uuid4()),session_id=context['session_id'],job_id=context.get('job_id'),
                    agent='planner',tool='arrange_learning',at=datetime.now(timezone.utc).isoformat(),
                    status='preparing',request=None,response=None,duration_ms=0,error=None)
        token=_call.set(record);started=time.monotonic();save(record)
        try:
            result=function(*args,**kwargs);record['status']='completed';return result
        except Exception as exc:
            record.update(status='failed',error={'code':getattr(exc,'code','internal_error'),
                          'stage':getattr(exc,'stage','workflow'),
                          'message':exc.message if hasattr(exc,'message') else '调用处理失败，查看课堂错误提示。'})
            raise
        finally:
            record['duration_ms']=round((time.monotonic()-started)*1000)
            _call.reset(token);save(record)
    return wrapped


def recent(session_id):
    db=connect()
    try:records=[json.loads(row[0]) for row in db.execute('SELECT record FROM planner_traces WHERE session_id=? ORDER BY started_at DESC,id DESC LIMIT ?',(session_id,LIMIT))]
    finally:db.close()
    return {'calls':records,'limit':LIMIT}
