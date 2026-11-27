from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from backend import chat_classroom as chat, teacher_styles as styles, board_detours, digital_board, usage
import test_api as api_fixture


class TeacherStyleTests(unittest.TestCase):
    def test_legacy_default_and_prompt_identity(self):
        state=chat.new_state();state.pop('teacher_style')
        self.assertEqual(chat.public(state)['teacher_style']['id'],'framework')
        self.assertEqual(len(styles.STYLES),3)
        self.assertEqual(len({s['prompt_hash'] for s in styles.STYLES.values()}),3)
        self.assertNotIn('prompt',styles.selected(state))

    def test_switch_changes_only_preference_and_preserves_question_progress_and_messages(self):
        state=chat.new_state();state.update(plan={'id':'p','goal':'目标','steps':['节点']},pending_question={'id':'q','question':'问题','rubric':'PRIVATE'})
        chat.ensure_outline(state);before=deepcopy(state)
        chat.event(state,'chat_teacher_style',{'style_id':'guided'})
        before['teacher_style']='guided';self.assertEqual(state,before)
        self.assertNotIn('PRIVATE',json.dumps(chat.public(state)))
        self.assertEqual(json.loads(json.dumps(state))['teacher_style'],'guided')

    def test_invalid_or_inflight_switch_is_atomic(self):
        state=chat.new_state()
        for payload in ({'style_id':'custom instructions'},{'style_id':['guided']},{'style_id':'guided','prompt':'override'}):
            before=deepcopy(state)
            with self.assertRaises(ValueError):chat.event(state,'chat_teacher_style',payload)
            self.assertEqual(state,before)
        chat.event(state,'chat_message',{'text':'请讲解','recipient':'lecturer'});before=deepcopy(state)
        with self.assertRaises(ValueError):chat.event(state,'chat_teacher_style',{'style_id':'guided'})
        self.assertEqual(state,before)

    def test_selected_prompt_and_identity_reach_actual_model_call_without_answer_key(self):
        for sid in styles.STYLES:
            state=chat.new_state();state['teacher_style']=sid
            state['pending_question']={'id':'q','question':'待答题','rubric':'PRIVATE'}
            chat.event(state,'chat_example',{})
            scopes=[]
            def model(*args,**kwargs):
                scopes.append(dict(usage._scope.get()))
                return {'tool':'submit_lecturer_result','arguments':{'message':'讲解','covered':'讲过','next_suggestion':'等待','visuals':[],'assessment_request':{'objective':'目标','covered':'讲过','prerequisites':'尚未确认','reason':'检查理解'}}}
            with patch.object(chat,'call_tool',side_effect=model) as call:
                chat.specialist(state,'lecturer','目标')
            system,data=call.call_args.args[:2]
            self.assertIn(styles.get(sid)['prompt'],system)
            self.assertEqual(data['classroom']['teacher_style']['id'],sid)
            self.assertNotIn('PRIVATE',json.dumps(data))
            self.assertEqual(scopes[0]['teacher_style_id'],sid)

    def test_style_never_leaks_into_assessment_instruction(self):
        state=chat.new_state();state['teacher_style']='guided'
        with patch.object(chat,'checked_call',return_value={}) as call:chat.specialist(state,'assessment','诊断')
        self.assertNotIn(styles.get('guided')['prompt'],call.call_args.args[0])

    def test_output_uses_frozen_job_identity_and_past_output_keeps_original_style(self):
        state=chat.new_state();chat.event(state,'chat_message',{'text':'讲一个概念','recipient':'lecturer'})
        state['teacher_style']='guided'  # Even an external preference edit cannot relabel a running job.
        response={'message':'正文','covered':'概念','next_suggestion':'等待','visuals':[],'assessment_request':{'objective':'目标','covered':'讲过','prerequisites':'尚未确认','reason':'检查理解'}}
        with patch.object(chat,'specialist',return_value=response):chat.run(state)
        lecture=next(m for m in state['messages'] if m['agent']=='lecturer' and m.get('status')=='ai')
        self.assertEqual(lecture['teacher_style']['id'],'framework')
        old=deepcopy(lecture)
        chat.event(state,'chat_teacher_style',{'style_id':'demonstration'})
        self.assertEqual(lecture,old)
        chat.event(state,'chat_message',{'text':'再举个例子','recipient':'lecturer'})
        self.assertEqual(state['job']['teacher_style']['id'],'demonstration')

    def test_detour_and_board_preserve_style_without_changing_question_contract(self):
        context={'teacher_style':styles.metadata('guided'),'return_anchor':{'title':'主线'}}
        with patch.object(board_detours,'call_tool',return_value={}) as call,patch.object(board_detours,'validate',return_value={}):board_detours.teach(context)
        self.assertIn(styles.get('guided')['prompt'],call.call_args.args[0])
        self.assertIn('不另出引导题或练习',call.call_args.args[0])
        source={'text':'正文','teacher_style':styles.metadata('guided')}
        with patch.object(digital_board,'call_tool',return_value={}) as call,patch.object(digital_board,'validate_board',return_value={}):digital_board.design(source,'基础未知')
        self.assertEqual(call.call_args.args[1]['teacher_style']['id'],'guided')
        self.assertIn('不把引导式讲解改写为直接公布答案',call.call_args.args[0])


class TeacherStyleApiTests(unittest.TestCase):
    setUpClass=classmethod(api_fixture.ApiTests.setUpClass.__func__)
    tearDownClass=classmethod(api_fixture.ApiTests.tearDownClass.__func__)
    call=api_fixture.ApiTests.call

    def test_public_prompt_catalog_and_initial_selection(self):
        code,catalog=self.call('/api/teacher-styles')
        self.assertEqual(code,200);self.assertEqual(len(catalog['styles']),3)
        self.assertTrue(all(s['prompt'] and s['prompt_hash'] for s in catalog['styles']))
        _,data=self.call('/api/sessions','POST',{'mode':'chat','teacher_style':'guided'})
        self.assertEqual(data['snapshot']['teacher_style']['id'],'guided')
        self.assertEqual(self.call('/api/sessions','POST',{'mode':'chat','teacher_style':'injected'})[0],422)

    def test_authenticated_persistent_idempotent_switch_and_revision_conflict(self):
        _,data=self.call('/api/sessions','POST',{'mode':'chat'})
        path='/api/sessions/'+data['session_id'];token=data['token'];before=data['snapshot']
        body={'expected_revision':before['revision'],'idempotency_key':'teacher-switch-1','type':'chat_teacher_style','payload':{'style_id':'demonstration'}}
        self.assertEqual(self.call(path+'/events','POST',body)[0],401)
        self.assertEqual(self.call(path+'/events','POST',body,'wrong')[0],404)
        code,result=self.call(path+'/events','POST',body,token)
        self.assertEqual(code,200)
        expected=deepcopy(before);expected['teacher_style']=styles.metadata('demonstration');expected['revision']+=1
        self.assertEqual(result['snapshot'],expected)
        self.assertTrue(self.call(path+'/events','POST',body,token)[1]['duplicate'])
        body['idempotency_key']='teacher-switch-2'
        self.assertEqual(self.call(path+'/events','POST',body,token)[0],409)
        restored=self.call(path,token=token)[1]['snapshot']
        self.assertEqual(restored,expected)
