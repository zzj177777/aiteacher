import copy
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_courses as helpers
from backend import curriculum


def candidate():
    return {'goal':'理解一次函数','assumptions':['基础需要确认'],'sections':[
        {'title':'函数含义','objective':'辨认函数的输入与输出','outcomes':['解释对应关系'],'prerequisite_indices':[],'estimated_minutes':15},
        {'title':'函数图像','objective':'认识函数图像','outcomes':['辨认一次函数图像'],'prerequisite_indices':[1],'estimated_minutes':20}]}


class CurriculumValidationTests(unittest.TestCase):
    def test_assigns_server_ids_and_resolves_ordered_dependencies(self):
        plan=curriculum.validate(candidate(),{'section_limit':12,'lesson_minutes':25})
        self.assertEqual([s['position'] for s in plan['sections']],[1,2])
        self.assertEqual(plan['sections'][1]['prerequisites'][0]['id'],plan['sections'][0]['id'])
        self.assertEqual(len({s['id'] for s in plan['sections']}),2)

    def test_rejects_cycles_future_refs_duplicates_large_lessons_and_bad_types(self):
        mutations=[lambda p:p['sections'][0].update(prerequisite_indices=[1]),
            lambda p:p['sections'][0].update(prerequisite_indices=[2]),
            lambda p:p['sections'][1].update(prerequisite_indices=[True]),
            lambda p:p['sections'][1].update(prerequisite_indices=[1,1]),
            lambda p:p['sections'][1].update(title='函数含义'),
            lambda p:p['sections'][0].update(estimated_minutes=40),
            lambda p:p['sections'][0].update(outcomes=[]),
            lambda p:p.update(sections=[])]
        for change in mutations:
            data=candidate();change(data)
            with self.assertRaises(ValueError):curriculum.validate(data,{'section_limit':12,'lesson_minutes':25})

    def test_wrong_tool_cannot_be_treated_as_a_plan(self):
        with patch.object(curriculum.tutor,'call_tool',return_value={'tool':'wrong','arguments':candidate()}):
            with self.assertRaises(ValueError):curriculum.generate({'title':'初中数学','description':''},{'section_limit':12,'lesson_minutes':25})


class CurriculumApiTests(unittest.TestCase):
    call=helpers.CourseApiTests.call
    library=helpers.CourseApiTests.library
    course=helpers.CourseApiTests.course
    lesson=helpers.CourseApiTests.lesson

    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.db=Path(cls.temp.name)/'classroom.sqlite3'
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));cls.port=sock.getsockname()[1]
        cls.url=f'http://127.0.0.1:{cls.port}'
        cls.env=dict(os.environ,COURSE_FIXTURE_PORT=str(cls.port),AITEACHER_DB=str(cls.db),
            AITEACHER_USAGE_DB=str(Path(cls.temp.name)/'usage.sqlite3'),AITEACHER_MODEL_DEBUG_DB=str(Path(cls.temp.name)/'debug.sqlite3'),
            AITEACHER_PLAIN_LANGUAGE_DB=str(Path(cls.temp.name)/'plain.sqlite3'))
        cls.start()

    @classmethod
    def start(cls):
        cls.process=subprocess.Popen([sys.executable,'tests/course_library_fixture.py'],cwd=Path(__file__).resolve().parents[1],env=cls.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        from urllib.request import urlopen
        for _ in range(80):
            try:
                with urlopen(cls.url+'/api/health',timeout=1):return
            except OSError:time.sleep(.1)
        raise RuntimeError('Curriculum fixture failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate();cls.process.wait(timeout=10);cls.temp.cleanup()

    def wait_plan(self,token,cid):
        for _ in range(60):
            result=self.call('/api/courses/'+cid,token=token)[1]['curriculum']
            if result['status']!='planning':return result
            time.sleep(.05)
        self.fail('Planning did not finish')

    def plan(self,token,cid,goal='学习一次函数',revision=0):
        status,result=self.call('/api/courses/'+cid+'/curriculum','POST',{'expected_revision':revision,'goal':goal,'background':'分数不熟','scope':'函数基础','lesson_minutes':25,'section_limit':8},token)
        self.assertEqual(status,200,result)
        return self.wait_plan(token,cid)

    def wait_session(self,token,sid):
        for _ in range(60):
            state=self.call('/api/sessions/'+sid,token=token)[1]['snapshot']
            if not state['working']:return state
            time.sleep(.05)
        self.fail('Session did not finish')

    def send(self,token,sid,kind,text=None):
        state=self.wait_session(token,sid)
        status,result=self.call('/api/sessions/'+sid+'/events','POST',{'expected_revision':state['revision'],'idempotency_key':str(uuid4()),'type':kind,'payload':{'text':text} if text else {}},token)
        self.assertEqual(status,200,result)
        return self.wait_session(token,sid)

    def test_generates_cards_and_records_course_scoped_usage(self):
        token=self.library();course=self.course(token);plan=self.plan(token,course['id'])
        self.assertEqual(plan['status'],'ready')
        self.assertEqual([s['position'] for s in plan['sections']],[1,2,3])
        self.assertIsNone(plan['sections'][0]['session'])
        self.assertEqual(plan['next_section_id'],plan['sections'][0]['id'])
        calls=self.call('/api/courses/'+course['id']+'/usage',token=token)[1]
        self.assertTrue(any(c['agent']=='course_planner' for c in calls['recent_calls']))
        self.assertEqual(calls['recent_calls'][0]['course_id'],course['id'])

    def test_opening_twice_restores_one_section_session_and_plans_local_nodes(self):
        token=self.library();course=self.course(token);cid=course['id'];plan=self.plan(token,cid);section=plan['sections'][0]
        path=f"/api/courses/{cid}/sections/{section['id']}/open"
        status,first=self.call(path,'POST',{},token);self.assertEqual(status,200,first)
        state=self.wait_session(token,first['session_id'])
        second=self.call(path,'POST',{},token)[1]
        self.assertEqual(second['session_id'],first['session_id'])
        self.assertEqual(state['section']['title'],section['title'])
        self.assertEqual(state['section']['course_learning_profile']['background'],'分数不熟')
        self.assertEqual(len(state['plan']['nodes']),3)
        self.assertEqual(len(self.call('/api/courses/'+cid,token=token)[1]['sessions']),1)
        with closing(sqlite3.connect(self.db)) as db:
            raw=json.loads(db.execute('SELECT state FROM sessions WHERE id=?',(first['session_id'],)).fetchone()[0])
        self.assertEqual(raw['job']['intent'],'section_intake')
        from concurrent.futures import ThreadPoolExecutor
        second_section=plan['sections'][1]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.call(f"/api/courses/{cid}/sections/{second_section['id']}/open",'POST',{},token),range(2)))
        self.assertTrue(all(result[0]==200 for result in results))
        self.assertEqual(results[0][1]['session_id'],results[1][1]['session_id'])
        self.wait_session(token,results[0][1]['session_id'])
        self.assertEqual(len(self.call('/api/courses/'+cid,token=token)[1]['sessions']),2)
        self.assertEqual(self.call('/api/learning-library/sessions/'+first['session_id'],'PATCH',{'course_id':None},token)[0],409)
        self.assertEqual(self.call('/api/courses/'+cid+'/curriculum','POST',{'expected_revision':plan['revision'],'goal':'学习一次函数'},token)[0],409)

    def test_confirmed_nodes_advance_recommended_section_not_mastery(self):
        token=self.library();course=self.course(token);cid=course['id'];plan=self.plan(token,cid);first=plan['sections'][0]
        opened=self.call(f"/api/courses/{cid}/sections/{first['id']}/open",'POST',{},token)[1];sid=opened['session_id']
        self.send(token,sid,'chat_message','开始吧')
        for _ in range(3):state=self.send(token,sid,'chat_continue')
        roadmap=self.call('/api/courses/'+cid,token=token)[1]['curriculum']
        self.assertEqual(roadmap['confirmed_sections'],1)
        self.assertEqual(roadmap['next_section_id'],plan['sections'][1]['id'])
        self.assertEqual(state['evidence'],[])
        self.assertFalse(state['completed'])

    def test_early_end_is_not_completed_section(self):
        token=self.library();course=self.course(token);cid=course['id'];plan=self.plan(token,cid)
        section=plan['sections'][0];sid=self.call(f"/api/courses/{cid}/sections/{section['id']}/open",'POST',{},token)[1]['session_id']
        self.send(token,sid,'chat_end')
        result=self.call('/api/courses/'+cid,token=token)[1]['curriculum']
        self.assertEqual(result['confirmed_sections'],0)
        self.assertEqual(result['next_section_id'],section['id'])

    def test_failed_plan_can_retry_and_unstarted_plan_can_be_replaced(self):
        token=self.library();course=self.course(token);cid=course['id']
        failed=self.plan(token,cid,'数学失败规划');self.assertEqual(failed['status'],'failed');self.assertFalse(failed['sections'])
        ready=self.plan(token,cid,revision=failed['revision']);self.assertEqual(ready['status'],'ready')
        again=self.plan(token,cid,revision=ready['revision']);self.assertEqual(again['status'],'ready')
        self.assertNotEqual(ready['sections'][0]['id'],again['sections'][0]['id'])
        self.assertEqual(self.call('/api/courses/'+cid+'/curriculum','POST',{'expected_revision':0,'goal':'一次函数'},token)[0],409)

    def test_course_change_during_generation_discards_old_result(self):
        token=self.library();course=self.course(token);cid=course['id']
        status,_=self.call('/api/courses/'+cid+'/curriculum','POST',{'goal':'数学慢速规划'},token);self.assertEqual(status,200)
        self.assertEqual(self.call('/api/courses/'+cid,'PATCH',{'title':'初二数学','description':'范围已调整'},token)[0],200)
        result=self.wait_plan(token,cid);self.assertEqual(result['status'],'failed');self.assertFalse(result['sections'])

    def test_other_space_and_other_course_cannot_open_or_plan(self):
        token,other=self.library(),self.library();course=self.course(token);cid=course['id'];plan=self.plan(token,cid)
        path=f"/api/courses/{cid}/sections/{plan['sections'][0]['id']}/open"
        self.assertEqual(self.call(path,'POST',{},other)[0],404)
        self.assertEqual(self.call('/api/courses/'+cid+'/curriculum','POST',{'goal':'一次函数'},other)[0],404)
        self.assertEqual(self.call('/api/courses/'+cid+'/usage',token=other)[0],404)
        another=self.course(token,'数学复习')
        self.assertEqual(self.call(f"/api/courses/{another['id']}/sections/{plan['sections'][0]['id']}/open",'POST',{},token)[0],404)
        self.assertEqual(self.call('/api/courses/'+cid,'PATCH',{'title':'初中英语'},token)[0],422)

    def test_restart_retains_section_links_and_marks_planning_interrupted(self):
        token=self.library();course=self.course(token);cid=course['id'];plan=self.plan(token,cid)
        section=plan['sections'][0];sid=self.call(f"/api/courses/{cid}/sections/{section['id']}/open",'POST',{},token)[1]['session_id'];self.wait_session(token,sid)
        another=self.course(token,'数学复习')
        with closing(sqlite3.connect(self.db)) as db,db:
            db.execute('INSERT INTO course_curricula VALUES(?,?,?,?,?,?,?,?)',(another['id'],1,'planning','lost-job',None,'{}',None,'now'))
        self.__class__.process.terminate();self.__class__.process.wait(timeout=10);self.__class__.start()
        reopened=self.call(f"/api/courses/{cid}/sections/{section['id']}/open",'POST',{},token)[1]
        self.assertEqual(reopened['session_id'],sid)
        self.assertEqual(self.call('/api/courses/'+another['id'],token=token)[1]['curriculum']['status'],'interrupted')
