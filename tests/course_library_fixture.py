"""Isolated course UI fixture; every model response is local and deterministic."""
import json
import asyncio
import os
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
(root/'.verification').mkdir(exist_ok=True)
port=int(os.getenv('COURSE_FIXTURE_PORT','8014'))
os.environ.update(AITEACHER_DB=os.getenv('AITEACHER_DB',str(root/'.verification'/'course-classroom.sqlite3')),
    AITEACHER_USAGE_DB=os.getenv('AITEACHER_USAGE_DB',str(root/'.verification'/'course-usage.sqlite3')),
    AITEACHER_MODEL_DEBUG_DB=os.getenv('AITEACHER_MODEL_DEBUG_DB',str(root/'.verification'/'course-debug.sqlite3')),
    AITEACHER_PLAIN_LANGUAGE_DB=os.getenv('AITEACHER_PLAIN_LANGUAGE_DB',str(root/'.verification'/'course-plain.sqlite3')),
    AI_API_URL=f'http://127.0.0.1:{port}/_fake_course_model',AI_API_KEY='local-course-test-key',AI_MODEL='course-test-model')
from backend.app import app
from fastapi import Request

observed=[]
observed_sections=[]
observed_school=[]

@app.post('/_fake_course_model')
async def fake_model(request:Request):
    body=await request.json()
    name=body['tools'][0]['function']['name']
    data=json.loads(body['messages'][-1]['content'])
    classroom=data.get('classroom',{})
    observed_school.append({'tool':name,'school_context':classroom.get('school_context')})
    if name=='arrange_learning':
        observed.append(classroom.get('course'))
        observed_sections.append(classroom.get('section'))
        goal=classroom.get('profile',{}).get('goal') or '一次函数'
        args=dict(action='teach' if classroom.get('plan') else 'plan',message='我们按三个小步骤学习，先确认这个计划。',
            reason='围绕本次小课的目标',goal=goal,background='初二，初学者',objective='理解函数的含义',
            steps=['理解含义','看一个例子','自己试一试'],plan_update='keep')
        if classroom.get('school_context'):
            school=classroom['school_context']
            goal=classroom.get('profile',{}).get('goal') or ('分数的意义' if school['subject_id']=='math' else '力的作用')
            args.update(goal=goal,message=f'我们先用两个小步骤学习{goal}，确认后开始。',
                background='仅知道学段和科目，具体年级和基础未知',objective=goal,
                steps=[goal,'结合生活例子检查'])
        if '偏题测试' in str(data.get('trigger','')):
            args.update(objective='学习英语语法',steps=['英语过去式','英语练习'])
    elif name=='suggest_learning_topics':
        physics=(classroom.get('school_context') or {}).get('subject_id')=='physics'
        args=dict(message='先挑一个感兴趣的小方向，也可以自己说想学什么。',choices=[
            dict(title=title,description='用一个容易懂的例子，从基础开始。') for title in (['力的作用','运动和静止','声音是怎样产生的'] if physics else ['分数的意义','乘法的含义','认识图形'])])
    elif name=='plan_course':
        inputs=data['learning_request']
        if '慢速规划' in inputs['goal']:await asyncio.sleep(1)
        args={'goal':inputs['goal'],'assumptions':['未指定教材，暂按通用函数知识规划；基础需要在课堂确认。'],'sections':[
            {'title':'函数的含义','objective':'解释函数的输入与输出','outcomes':['辨认输入与输出','说明什么是对应关系'],'prerequisite_indices':[],'estimated_minutes':min(15,inputs['lesson_minutes'])},
            {'title':'函数的表示','objective':'用表格和图像表示函数','outcomes':['把对应关系表示成表格'],'prerequisite_indices':[1],'estimated_minutes':min(20,inputs['lesson_minutes'])},
            {'title':'一次函数入门','objective':'辨认一次函数的图像','outcomes':['解释斜率的直观含义'],'prerequisite_indices':[2],'estimated_minutes':inputs['lesson_minutes']}]}
        if '失败规划' in inputs['goal']:args['sections'][0]['prerequisite_indices']=[3]
    elif name=='check_course_scope':
        topic=data['request']
        args=dict(decision='redirect' if '英语语法' in topic or '忽略' in topic or '做饭' in topic else 'allow',reason='检查课程方向与当前请求的关系。')
    elif name=='submit_lecturer_result':
        args=dict(message='函数描述两个量一起变化的关系。一个输入对应一个输出。',covered='函数的含义',next_suggestion='结合例子检查',visuals=[])
        if classroom.get('school_context'):
            args.update(message='把一个整体平均分成几份，分数就能表示其中的一份或几份。',covered=classroom.get('profile',{}).get('goal','分数的意义'))
        args['assessment_request']={'objective':'检查本节理解','covered':args['covered'],'prerequisites':'尚未确认','reason':'本小节讲解完成'}
    elif name=='explain_lecture_plainly':
        args=dict(takeaway='先看一个输入和对应的输出。',concepts=[])
    else:
        raise RuntimeError('Unexpected fixture model tool')
    return {'model':body['model'],'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
        'tool_calls':[{'id':name,'type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}}],
        'usage':{'prompt_tokens':40,'completion_tokens':50}}

@app.get('/_observed_courses')
def observed_courses():
    return observed

@app.get('/_observed_sections')
def section_requests():
    return observed_sections


@app.get('/_observed_school')
def school_requests():
    return observed_school

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=port)
