"""Isolated fake model for the real lecture -> plain-language HTTP flow."""
import asyncio
import json
import os
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
os.environ.update(AITEACHER_DB=str(root/'.verification'/'plain-classroom.sqlite3'),
    AITEACHER_USAGE_DB=str(root/'.verification'/'plain-usage.sqlite3'),
    AITEACHER_MODEL_DEBUG_DB=str(root/'.verification'/'plain-debug.sqlite3'),
    AITEACHER_PLAIN_LANGUAGE_DB=str(root/'.verification'/'plain-explanations.sqlite3'),
    AI_API_URL='http://127.0.0.1:8012/_fake_plain_model',AI_API_KEY='local-plain-test-key',AI_MODEL='plain-test-model')
from backend.app import app
from fastapi import Request

attempts={}
DEMO=(
    '今天先把分数里的三个关系弄清楚。\n\n'
    '**平均分**不是随便分几块，而是每份一样大。\n'
    '把一张饼分给四个人，如果有人拿得多、有人拿得少，就不能直接把每一块都当成同样的一份。我们先约定好，每份的大小相同，再谈分数。\n\n'
    '这个约定非常重要。后面数“几份”时，大家数的才是同样大小的单位，就像量长度前要先说清楚用厘米还是米。\n\n'
    '**分母**表示把整体平均分成了多少份。\n'
    '先认清什么是一个整体。一张饼是整体，一条线段也可以是整体。分母数的是平均分的总份数，不是饼的重量，也不是拿走的数量。\n\n'
    '例如同样一张饼，平均分成2份和平均分成4份，每一份的大小就不同。所以比较分数时，不能只看某个数字大不大。\n\n'
    '$\\frac{1}{4}$ 表示把整体平均分成4份，取其中1份。\n'
    '分数线上面的数回答“取了几份”，下面的数回答“一共平均分成几份”。把这两个问题分开问，读分数就不容易混淆。\n\n'
    '先把这三句话对应起来，暂时不急着做分数加减。')

@app.post('/_fake_plain_model')
async def fake_model(request:Request):
    body=await request.json();name=body['tools'][0]['function']['name'];data=json.loads(body['messages'][-1]['content'])
    if name=='submit_lecturer_result':
        objective=data['objective']
        term='分子' if '分子' in objective else '分母'
        text='分子表示取了其中几份。它写在分数线的上面。' if term=='分子' else '分母表示把整体平均分成了多少份。每一份必须一样大。'
        if '辅助失败' in objective:text+='（模拟辅助失败）'
        args={'message':text+'\n\n把一张饼平均分成4块，拿走其中1块，可以写成 $\\frac{1}{4}$。你想再看一个例子吗？',
              'covered':term+'的含义','next_suggestion':'检查理解','visuals':[]}
        args['assessment_request']={'objective':objective,'covered':args['covered'],'prerequisites':'尚未确认','reason':'检查理解'}
        if '批注演示' in objective:args['message']=DEMO
    elif name=='explain_lecture_plainly':
        key=data['source_message_id'];attempts[key]=attempts.get(key,0)+1
        term='分子' if data['lecture'].startswith('分子') else '分母'
        await asyncio.sleep(.4 if term=='分子' else 3)
        quote='分子表示取了其中几份。' if term=='分子' else '分母表示把整体平均分成了多少份。'
        if '模拟辅助失败' in data['lecture'] and attempts[key]==1:quote='这是原文中不存在的引用。'
        args={'takeaway':'分子看拿了多少份。' if term=='分子' else '分母看一共平均分成几份。','concepts':[{
            'term':term,'quote':quote,'why_difficult':'可能把拿了几份和一共分成几份混淆。','explanation':'它告诉你，分好的东西拿了几份。' if term=='分子' else '它告诉你，一整个东西被平均分成几份。',
            'example':'一张饼分成4块，拿走1块，分子就是1。' if term=='分子' else '把一张饼平均分成4块，分母就是4。',
            'boundary':'每块都必须一样大。'}]}
        if data['lecture'].startswith('今天'):
            args={'takeaway':'先确定平均分，再区分总份数和取的份数。','concepts':[
                {'term':'平均分','quote':'**平均分**不是随便分几块，而是每份一样大。','why_difficult':'可能把分成几块误当成平均分。','explanation':'每份都一样大，才能用同样的一份来数。','example':'把一张饼分给4个人，每个人拿到的大小要一样。','boundary':'不是看到4块就一定是平均分。'},
                {'term':'分母数的是什么','quote':'**分母**表示把整体平均分成了多少份。','why_difficult':'可能混淆总共分的份数和拿走的份数。','explanation':'分母只回答：一整个东西被平均分成了几份。','example':'整张饼平均切成4块，不管拿走几块，分母都是4。','boundary':''},
                {'term':'分数写法','quote':'$\\frac{1}{4}$ 表示把整体平均分成4份，取其中1份。','why_difficult':'上下两个数字分别代表什么容易弄反。','explanation':'下面看一共分几份，上面看取了几份。','example':'切成4份取1份，就写成四分之一。','boundary':''}]}
    else:
        args={'action':'teach','message':'从一个小概念开始。','reason':'根据学生提问',
              'goal':'理解分数','background':'学生自述初学','objective':'理解分母',
              'steps':['分母','分子'],'plan_update':'keep'}
    return {'model':body['model'],'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
        'tool_calls':[{'id':name,'type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}}],
        'usage':{'prompt_tokens':100,'completion_tokens':80}}

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8012)
