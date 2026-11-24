import json
import unittest
from unittest.mock import patch
from backend.lesson import apply_event, new_state, public_state
from backend.lecturer import current_task, dispatch
from backend.teaching_session import unit, upgrade_legacy, settle_generation
from backend.teaching_content import PLANS
from test_lesson import complete_lecture


class TeachingSessionTests(unittest.TestCase):
    def prepare(self):
        s=new_state()
        with patch('backend.lecturer.configured',return_value=False):
            for _ in range(3):
                apply_event(s,'submit_diagnostic_answer',{'choice':0})
        return s

    def check(self,s,answer):
        t=current_task(s)
        with patch('backend.tutor.configured',return_value=False):
            return apply_event(s,'submit_teaching_check',{'task_id':t['id'],'check_id':t['session']['check_id'],'answer':answer})

    def test_no_skip_and_only_one_point_at_a_time(self):
        s=self.prepare(); t=current_task(s)
        self.assertEqual(t['session']['segment_index'],0)
        for action in ['finish_lecture','next_teaching_segment']:
            with self.assertRaises(ValueError):
                apply_event(s,action,{})
        self.check(s,1)
        self.assertEqual(t['session']['segment_status'],'passed')
        self.assertEqual(t['session']['segment_index'],0)
        apply_event(s,'next_teaching_segment',{})
        self.assertEqual(t['session']['segment_index'],1)
        self.assertFalse(s['completed'])

    def test_wrong_answer_remedies_same_point_with_new_check(self):
        s=self.prepare(); t=current_task(s)
        old=t['session']['check_id']; prompt=public_state(s)['teaching_task']['segment']['check']['prompt']
        self.assertFalse(self.check(s,0)['correct'])
        self.assertEqual(t['session']['segment_index'],0)
        self.assertEqual(t['session']['generation_mode'],'remedial')
        self.assertNotEqual(old,t['session']['check_id'])
        self.assertNotEqual(prompt,public_state(s)['teaching_task']['segment']['check']['prompt'])
        self.assertEqual(len(t['session']['checks']),1)
        with self.assertRaises(ValueError):
            apply_event(s,'submit_teaching_check',{'task_id':t['id'],'check_id':old,'answer':1})

    def test_repeated_wrong_answer_stays_needs_review(self):
        s=self.prepare(); t=current_task(s)
        for wrong in [0,0,1]: self.check(s,wrong)
        self.assertEqual(t['session']['segment_status'],'needs_review')
        self.assertEqual(t['session']['segment_index'],0)
        with self.assertRaises(ValueError): apply_event(s,'next_teaching_segment',{})
        apply_event(s,'pause_lecture',{})
        self.assertEqual(s['phase'],'guided_practice')
        self.assertFalse(s['completed'])

    def test_public_snapshot_has_no_check_keys(self):
        s=self.prepare(); p=public_state(s)
        self.assertNotIn('teaching_tasks',p)
        check=p['teaching_task']['segment']['check']
        self.assertNotIn('answer',check); self.assertNotIn('explanation',check)
        self.assertNotIn('checks',p['teaching_task']['segment'])

    def test_session_persists_and_resumes_exact_point(self):
        s=self.prepare(); self.check(s,1); apply_event(s,'next_teaching_segment',{})
        t=current_task(s); task_id=t['id']; check_id=t['session']['check_id']
        before=s['matrix']
        apply_event(s,'pause_lecture',{})
        self.assertIsNone(current_task(s))
        s=json.loads(json.dumps(s))
        self.assertEqual(public_state(s)['paused_teaching_tasks'][0]['id'],task_id)
        apply_event(s,'resume_lecture',{'task_id':task_id})
        t=current_task(s)
        self.assertEqual(t['session']['segment_index'],1)
        self.assertEqual(t['session']['check_id'],check_id)
        self.assertEqual(t['session']['passed_segments'],[0])
        self.assertEqual(s['matrix'],before)

    def test_questions_remembered_until_student_resolves(self):
        s=self.prepare()
        with patch('backend.tutor.configured',return_value=False):
            result=apply_event(s,'ask_question',{'text':'主对角线是什么？'})
        t=current_task(s)
        self.assertEqual(t['session']['segment_index'],0)
        q=t['session']['open_questions'][0]
        self.assertEqual(q['status'],'answered')
        apply_event(s,'resolve_teaching_question',{'question_id':result['message_id']})
        self.assertEqual(t['session']['open_questions'],[])
        self.assertEqual(len(t['session']['resolved_questions']),1)

    def test_pending_question_cannot_be_prematurely_resolved(self):
        s=self.prepare()
        with patch('backend.tutor.configured',return_value=True):
            result=apply_event(s,'ask_question',{'text':'什么是主元？'})
        with self.assertRaises(ValueError):
            apply_event(s,'resolve_teaching_question',{'question_id':result['message_id']})

    def test_invalid_numeric_answer_does_not_consume_check(self):
        s=self.prepare(); self.check(s,1); apply_event(s,'next_teaching_segment',{})
        t=current_task(s)
        with self.assertRaises(ValueError): self.check(s,'1/0')
        self.assertEqual(t['session']['attempts'],0)
        self.assertEqual(t['session']['segment_status'],'awaiting_check')

    def test_all_topic_plans_complete_without_mastery_claim(self):
        for topic in PLANS:
            with self.subTest(topic=topic):
                s=new_state(); s['phase']='guided_practice'
                with patch('backend.lecturer.configured',return_value=False): dispatch(s,topic)
                complete_lecture(s)
                self.assertEqual(s['phase'],'guided_practice')
                self.assertFalse(s['completed'])
                self.assertEqual(len(s['teaching_tasks'][0]['session']['passed_segments']),3)

    def test_legacy_active_lecture_migrates_without_losing_records(self):
        s=self.prepare(); t=current_task(s)
        del t['session']; del t['protocol']
        old_message_count=len(s['messages'])
        self.assertTrue(upgrade_legacy(s))
        self.assertEqual(current_task(s)['session']['segment_index'],0)
        self.assertGreater(len(s['messages']),old_message_count)
        self.assertFalse(upgrade_legacy(s))

    def test_pause_invalidates_in_flight_generation(self):
        s=self.prepare(); t=current_task(s)
        t['status']='pending'; t['session']['segment_status']='generating'
        old_generation=t['session']['generation_id']
        apply_event(s,'pause_lecture',{})
        self.assertNotEqual(t['session']['generation_id'],old_generation)
        self.assertEqual(t['session']['segment_status'],'awaiting_check')
