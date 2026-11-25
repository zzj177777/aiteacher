"""Independent per-call ledger. Never stores prompts, answers, or credentials."""
import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from uuid import uuid4

_scope=ContextVar('usage_scope',default={})
_call=ContextVar('usage_call',default=None)

@contextmanager
def scope(**values):
    token=_scope.set({**_scope.get(),**values})
    try:yield
    finally:_scope.reset(token)


def path():
    return Path(os.getenv('AITEACHER_USAGE_DB',str(Path(__file__).resolve().parents[1]/'data'/'model_usage.sqlite3')))


def connect():
    target=path();target.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(target,timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS model_calls(id TEXT PRIMARY KEY, session_id TEXT, record TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS model_calls_session ON model_calls(session_id)')
    return db


def count(value):return value if type(value) is int and value>=0 else None


def capture(result):
    record=_call.get()
    if record is None:return
    usage=result.get('usage',{}) if isinstance(result,dict) else {}
    if not isinstance(usage,dict):usage={}
    for key in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens'):
        record[key]=count(usage.get(key))


def price(record):
    record.update(estimated_cost=None,currency=os.getenv('AI_PRICE_CURRENCY','CNY'),pricing_status='unconfigured')
    if os.getenv('AI_PRICE_MODEL')!=record['model']:return
    def rate(name):
        value=Decimal(os.environ[name])
        if not value.is_finite() or value<0:raise ValueError()
        return value
    try:
        incoming=rate('AI_INPUT_PRICE_PER_MILLION');outgoing=rate('AI_OUTPUT_PRICE_PER_MILLION')
        prompt=record.get('prompt_tokens');output=record.get('completion_tokens')
        if prompt is None or output is None:
            record['pricing_status']='usage_unavailable';return
        hit=record.get('prompt_cache_hit_tokens')
        if hit is not None and hit>prompt:raise ValueError()
        if hit is not None and 'AI_CACHE_HIT_PRICE_PER_MILLION' in os.environ:
            total=Decimal(prompt-hit)*incoming+Decimal(hit)*rate('AI_CACHE_HIT_PRICE_PER_MILLION')+Decimal(output)*outgoing
            basis='cache_aware'
        else:
            total=Decimal(prompt)*incoming+Decimal(output)*outgoing;basis='standard_input_rate'
        record.update(estimated_cost=float(total/Decimal(1000000)),pricing_status='estimated',pricing_basis=basis,
                      rates={'input':str(incoming),'output':str(outgoing),'cache_hit':os.getenv('AI_CACHE_HIT_PRICE_PER_MILLION')})
    except (KeyError,InvalidOperation,ValueError):record['pricing_status']='invalid_or_missing_rates'


def metered(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        record=dict(id=str(uuid4()),**_scope.get(),model=os.getenv('AI_MODEL','unconfigured'),
                    at=datetime.now(timezone.utc).isoformat(),status='completed')
        token=_call.set(record);start=time.monotonic()
        try:return function(*args,**kwargs)
        except Exception as exc:
            record.update(status='failed',error_code=getattr(exc,'code','internal_error'))
            raise
        finally:
            record['duration_ms']=round((time.monotonic()-start)*1000)
            price(record);_call.reset(token)
            try:
                db=connect()
                try:
                    with db:db.execute('INSERT INTO model_calls VALUES(?,?,?)',(record['id'],record.get('session_id'),json.dumps(record,ensure_ascii=False)))
                finally:db.close()
            except Exception:
                logging.getLogger(__name__).error('usage_record_write_failed call_id=%s',record['id'])
    return wrapped


def summary(session_id=None,*,course_id=None):
    db=connect()
    try:
        if course_id is not None:
            rows=db.execute("SELECT record FROM model_calls WHERE json_extract(record,'$.course_id')=? ORDER BY rowid",(course_id,))
        elif session_id is not None:
            rows=db.execute('SELECT record FROM model_calls WHERE session_id=? ORDER BY rowid',(session_id,))
        else:raise ValueError('A session or course scope is required.')
        records=[json.loads(row[0]) for row in rows]
    finally:db.close()
    costs={}
    for record in records:
        if record['estimated_cost'] is not None:
            currency=record['currency'];costs[currency]=costs.get(currency,0)+record['estimated_cost']
    return dict(call_count=len(records),failed_calls=sum(r['status']=='failed' for r in records),
                prompt_tokens=sum(r.get('prompt_tokens') or 0 for r in records),
                completion_tokens=sum(r.get('completion_tokens') or 0 for r in records),
                usage_unknown_calls=sum(r.get('prompt_tokens') is None or r.get('completion_tokens') is None for r in records),
                unpriced_calls=sum(r['estimated_cost'] is None for r in records),estimated_costs=costs,
                duration_ms=sum(r['duration_ms'] for r in records),recent_calls=records[-30:])
