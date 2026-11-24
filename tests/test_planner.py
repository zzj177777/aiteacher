import copy
import unittest
from unittest.mock import patch
from backend import planner, tutor
from backend.lesson import new_state, apply_event, public_state


class PlannerTests(unittest.TestCase):
    def state(self, request='我想学三阶行列式，基础一般，有20分钟'):
        state = new_state()
        planner.initialize(state, onboarding=True)
        planner.handle_message(state, {'text': request})
        return state

    def confirmed(self):
        state = self.state()
        planner.execute(state, planner.fallback_decision(state), 'fallback')
        planner.confirm(state, {'plan_id': state['planner']['plan']['id']})
        return state

    def test_plan_requires_explicit_confirmation(self):
        state = self.state()
        self.assertNotIn('start_teaching', planner.allowed_tools(state))
        planner.execute(state, planner.fallback_decision(state), 'fallback')
        self.assertEqual(state['phase'], 'planning')
        self.assertFalse(state['planner']['course_confirmed'])
        with self.assertRaises(ValueError): planner.confirm(state, {'plan_id': 'old'})
        planner.confirm(state, {'plan_id': state['planner']['plan']['id']})
        planner.execute(state, planner.fallback_decision(state), 'fallback')
        self.assertEqual(state['phase'], 'diagnosis')

    def test_diagnostic_completion_dispatches_existing_teacher(self):
        state = self.confirmed()
        planner.execute(state, planner.fallback_decision(state), 'fallback')
        for _ in range(3): apply_event(state, 'submit_diagnostic_answer', {'choice': 0})
        self.assertEqual(state['planner']['job']['trigger'], 'diagnostic_completed')
        with patch('backend.tutor.configured', return_value=False):
            planner.execute(state, planner.fallback_decision(state), 'fallback')
        self.assertEqual(state['phase'], 'lecture')
        self.assertIsNotNone(state['active_teaching_task'])

    def test_unsupported_goal_cannot_be_silently_replaced(self):
        decision = planner.fallback_decision(self.state())
        state = self.state('我想学积分，导数不太熟')
        with self.assertRaises(ValueError): planner.validate(state, decision)
        decision['arguments']['course_id'] = 'unavailable'
        decision['arguments']['goal'] = '学习积分'
        planner.execute(state, decision, 'ai')
        self.assertFalse(state['planner']['plan']['executable'])
        with self.assertRaises(ValueError): planner.confirm(state, {'plan_id':state['planner']['plan']['id']})

    def test_unknown_fields_and_fabricated_scores_rejected(self):
        state = self.state()
        decision = planner.fallback_decision(state)
        decision['arguments']['mastery'] = 1
        with self.assertRaises(ValueError): planner.validate(state, decision)
        with self.assertRaises(ValueError): planner.validate(state, {'tool':'set_score','arguments':{}})

    def test_assessment_requires_completed_problem(self):
        state = self.confirmed()
        self.assertNotIn('start_assessment', planner.allowed_tools(state))
        self.assertNotIn('end_session', planner.allowed_tools(state))

    def test_new_request_replaces_pending_job(self):
        state = self.state()
        old = state['planner']['job']['id']
        planner.handle_message(state, {'text':'我想先学换行变号'})
        self.assertNotEqual(old, state['planner']['job']['id'])
        self.assertEqual(sum(m.get('agent')=='planner' and m.get('status')=='pending' for m in state['messages']), 1)

    def test_public_projection_hides_internal_jobs(self):
        state = self.state()
        projected = public_state(state)['planner']
        self.assertNotIn('job', projected)
        self.assertNotIn('turns', projected)
        self.assertEqual(projected['profile']['source'], 'conversation_summary_unverified')

    def test_model_decision_is_validated(self):
        state = self.state()
        with patch('backend.planner.call_tool', return_value={'tool':'invented','arguments':{}}):
            with self.assertRaises(ValueError): planner.remote_decision(state)

    def test_negative_end_request_cannot_end_session(self):
        state = self.state('不要结束学习')
        self.assertNotIn('end_session', planner.allowed_tools(state))

    def test_native_tool_response_parsing(self):
        response = {'choices':[{'message':{'tool_calls':[{'function':{'name':'ask_student','arguments':'{"message":"hello","reason":"clarify","options":[]}'}}]}}]}
        with patch.dict('os.environ', {'AI_MODEL':'test','AI_API_KEY':'test','AI_API_URL':'https://example.test'}), patch('backend.tutor.request_completion', return_value=response):
            self.assertEqual(tutor.call_tool('system', {}, [])['tool'], 'ask_student')

    def test_prose_and_multiple_calls_cannot_execute(self):
        for calls in ([], [{}, {}]):
            with patch.dict('os.environ', {'AI_MODEL':'test','AI_API_KEY':'test','AI_API_URL':'https://example.test'}), patch('backend.tutor.request_completion', return_value={'choices':[{'message':{'content':'start teaching','tool_calls':calls}}]}):
                with self.assertRaises(ValueError): tutor.call_tool('system', {}, [])

