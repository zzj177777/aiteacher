from copy import deepcopy
import json
import sqlite3
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fastapi import HTTPException
from backend import teacher_styles as styles, chat_classroom as chat, board_detours, usage
import test_api as api_fixture


class CustomStyleTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;styles.initialize(self.db);self.addCleanup(self.db.close)
        self.owner='owner-a-'*8
        self.custom=styles.create(self.db,self.owner,'先问再演示','先确认困难，再演示一个小步骤。','学生：不会。\n老师：先看一个最小例子。','create-custom-1')

    def test_catalog_and_resolution_are_owner_scoped_and_creation_is_idempotent(self):
        self.assertEqual(len(styles.catalog(self.db)),3)
        self.assertEqual(len(styles.catalog(self.db,'owner-b-'*8)),3)
        self.assertEqual(len(styles.catalog(self.db,self.owner)),4)
        self.assertEqual(styles.resolve(self.db,self.custom['id'],self.owner),self.custom)
        for owner in ('','owner-b-'*8):
            with self.assertRaises(HTTPException) as caught:styles.resolve(self.db,self.custom['id'],owner)
            self.assertEqual(caught.exception.status_code,404)
        duplicate=styles.create(self.db,self.owner,self.custom['name'],self.custom['approach'],self.custom['examples'],'create-custom-1')
        self.assertEqual(duplicate,self.custom)
        with self.assertRaises(HTTPException):styles.create(self.db,self.owner,'另一个名称','另一个思路','示例','create-custom-1')
        self.assertEqual(len(styles.catalog(self.db,self.owner)),4)

    def test_custom_config_survives_serialization_and_freezes_per_job_without_leaking_owner_or_rubric(self):
        state=chat.new_state();original=deepcopy(state)
        chat.event(state,'chat_teacher_style',{'style_id':self.custom['id']},style_config=self.custom)
        for key in ('messages','plan','pending_question','evidence'):self.assertEqual(state[key],original[key])
        state=json.loads(json.dumps(state));self.assertEqual(chat.public(state)['teacher_style']['name'],self.custom['name'])
        self.assertNotIn('teacher_style_config',chat.public(state))
        state['pending_question']={'question':'待答题','rubric':'PRIVATE-RUBRIC'}
        chat.event(state,'chat_example',{})
        frozen=deepcopy(state['job']['teacher_style_config'])
        state['teacher_style_config']['approach']='后来的修改'
        captures=[]
        def model(*args,**kwargs):
            captures.append(dict(usage._scope.get()))
            return {'message':'小例子','covered':'当前概念','next_suggestion':'等待','visuals':[]}
        with patch.object(chat,'checked_call',side_effect=model) as call:chat.specialist(state,'lecturer','举一个不同情境的例子')
        system,data=call.call_args.args[:2]
        self.assertIn(frozen['prompt'],system);self.assertNotIn('PRIVATE-RUBRIC',json.dumps(data))
        self.assertNotIn(self.owner,system+json.dumps(data));self.assertEqual(captures[0]['teacher_style_id'],self.custom['id'])
        self.assertEqual(styles.turn_definition(state),frozen)

    def test_builtin_switch_clears_custom_and_assessment_ignores_custom_prompt(self):
        state=chat.new_state();styles.apply(state,self.custom['id'],self.custom)
        with patch.object(chat,'checked_call',return_value={}) as call:chat.specialist(state,'assessment','诊断')
        self.assertNotIn(self.custom['prompt'],call.call_args.args[0])
        chat.event(state,'chat_teacher_style',{'style_id':'guided'})
        self.assertNotIn('teacher_style_config',state)
        self.assertEqual(styles.selected(state)['id'],'guided')

    def test_detour_uses_custom_system_prompt_without_copying_private_config_to_context(self):
        context={'teacher_style':styles.describe(self.custom),'_teacher_style_config':self.custom,'return_anchor':{'title':'原位置'}}
        with patch.object(board_detours,'call_tool',return_value={}) as call,patch.object(board_detours,'validate',return_value={}):board_detours.teach(context)
        self.assertIn(self.custom['prompt'],call.call_args.args[0])
        self.assertNotIn('_teacher_style_config',call.call_args.args[1])
        self.assertIn('不另出引导题或练习',call.call_args.args[0])


class CustomStyleApiTests(unittest.TestCase):
    setUpClass=classmethod(api_fixture.ApiTests.setUpClass.__func__)
    tearDownClass=classmethod(api_fixture.ApiTests.tearDownClass.__func__)

    def call(self,path,method='GET',body=None,token=None,owner=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        if owner:headers['X-Teacher-Style-Token']=owner
        req=Request(self.url+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urlopen(req,timeout=5) as response:return response.status,json.load(response)
        except HTTPError as exc:return exc.code,json.load(exc)

    def test_create_reload_select_new_session_and_restore_without_style_token(self):
        owner='private-style-owner-'*3
        body={'name':'画面感老师','approach':'先给场景，再解释对应关系。','examples':'学生：什么是分数？老师：把同一张饼分成相等的份。','idempotency_key':'api-create-custom-1'}
        self.assertEqual(self.call('/api/teacher-styles','POST',body)[0],401)
        code,result=self.call('/api/teacher-styles','POST',body,owner=owner);self.assertEqual(code,201)
        style=result['style'];sid=style['id'];self.assertTrue(sid.startswith('custom_'))
        self.assertEqual(self.call('/api/teacher-styles','POST',body,owner=owner)[1]['style']['id'],sid)
        self.assertNotIn(sid,json.dumps(self.call('/api/teacher-styles')[1]))
        self.assertIn(sid,json.dumps(self.call('/api/teacher-styles',owner=owner)[1]))
        self.assertEqual(self.call('/api/sessions','POST',{'mode':'chat','teacher_style':sid},owner='another-owner-'*4)[0],404)
        _,session=self.call('/api/sessions','POST',{'mode':'chat','teacher_style':sid},owner=owner)
        path='/api/sessions/'+session['session_id'];token=session['token']
        self.assertEqual(session['snapshot']['teacher_style']['name'],body['name'])
        restored=self.call(path,token=token)[1]['snapshot']
        self.assertEqual(restored,session['snapshot']);self.assertNotIn('teacher_style_config',restored)
        event={'expected_revision':restored['revision'],'idempotency_key':'style-switch-builtin','type':'chat_teacher_style','payload':{'style_id':'guided'}}
        code,changed=self.call(path+'/events','POST',event,token=token);self.assertEqual(code,200)
        event.update(expected_revision=changed['snapshot']['revision'],idempotency_key='style-switch-custom',payload={'style_id':sid})
        self.assertEqual(self.call(path+'/events','POST',event,token=token)[0],404)
        code,changed=self.call(path+'/events','POST',event,token=token,owner=owner);self.assertEqual(code,200)
        self.assertEqual(changed['snapshot']['teacher_style']['prompt_hash'],style['prompt_hash'])
        self.assertEqual(changed['snapshot']['messages'],restored['messages'])

    def test_required_fields_input_limits_and_payload_spoofing(self):
        owner='validation-owner-'*4
        valid={'name':'名称','approach':'思路','examples':'示例','idempotency_key':'validation-1'}
        for key,value in [('name',' '),('approach',' '),('examples',''),('name','a'*81)]:
            self.assertEqual(self.call('/api/teacher-styles','POST',{**valid,key:value},owner=owner)[0],422)
        _,session=self.call('/api/sessions','POST',{'mode':'chat'})
        body={'expected_revision':0,'idempotency_key':'spoofing-1','type':'chat_teacher_style','payload':{'style_id':{'prompt':'override'}}}
        self.assertEqual(self.call('/api/sessions/'+session['session_id']+'/events','POST',body,token=session['token'],owner=owner)[0],422)
