"""Isolated local fake provider: exercises the real HTTP model adapter without billing."""
import asyncio
import json
import os
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
os.environ.update(AITEACHER_DB=str(root/'.verification'/'debug-classroom.sqlite3'),
    AITEACHER_USAGE_DB=str(root/'.verification'/'debug-usage.sqlite3'),
    AITEACHER_MODEL_DEBUG_DB=str(root/'.verification'/'debug-traces.sqlite3'),
    AI_API_URL='http://127.0.0.1:8012/_fake_model',AI_API_KEY='local-test-key-only',AI_MODEL='debug-model-test')
from backend.app import app
from fastapi import Request

@app.post('/_fake_model')
async def fake_model(request:Request):
    body=await request.json()
    data=json.loads(body['messages'][-1]['content'])
    trigger=json.dumps(data.get('trigger'),ensure_ascii=False)
    await asyncio.sleep(2)
    arguments={'action':'plan','message':'先从平均分开始，再认识分数。你想按这个计划开始吗？',
        'reason':'根据学生目标形成初步计划','goal':'理解分数','background':'学生自述初学',
        'objective':'理解平均分','steps':['平均分','认识分数'],'plan_update':'keep'}
    raw='{invalid original tool arguments' if 'invalid-json' in trigger else json.dumps(arguments,ensure_ascii=False)
    return {'id':'local-provider-response','model':body['model'],'choices':[{'finish_reason':'tool_calls',
        'message':{'role':'assistant','content':None,'reasoning_content':'PRIVATE_REASONING_TEST',
        'tool_calls':[{'id':'local-tool','type':'function','function':{'name':'arrange_learning','arguments':raw}}]}}],
        'usage':{'prompt_tokens':200,'completion_tokens':100}}

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8012)
