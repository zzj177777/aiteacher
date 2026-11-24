import unittest
from unittest.mock import patch
from backend.lesson import new_state, apply_event, public_state
from backend.lecturer import dispatch, current_task, remote_lecture
from test_lesson import complete_lecture


class LecturerTests(unittest.TestCase):
    def prepare(self):
        state = new_state()
        for choice in (1, 0, 0):
            apply_event(state, 'submit_diagnostic_answer', {'choice': choice})
        return state

    def test_task_is_explicit_and_handoffs_are_real(self):
        with patch('backend.lecturer.configured', return_value=False):
            state = self.prepare()
        task = current_task(state)
        self.assertEqual(state['phase'], 'lecture')
        self.assertEqual(task['topic'], 'triangular_method')
        self.assertEqual(task['to_agent'], 'lecturer')
        self.assertIn('−6', task['focus'][0])
        self.assertTrue(task['objective'])
        self.assertTrue(task['constraints'])
        self.assertTrue(any(m.get('to_agent') == 'lecturer' and m.get('task_id') == task['id'] for m in state['messages']))
        self.assertFalse(any(m.get('to_agent') == 'scheduler' and m.get('task_id') == task['id'] for m in state['messages']))
        self.assertEqual(task['session']['segment_index'],0)
        self.assertEqual(public_state(state)['agents']['scheduler']['implementation'], 'state_machine')

    def test_lecture_does_not_advance_or_mark_mastery(self):
        with patch('backend.lecturer.configured', return_value=False):
            state = self.prepare()
        self.assertFalse(state['completed'])
        with self.assertRaises(ValueError):
            apply_event(state,'submit_final_answer',{'answer':'1'})
        complete_lecture(state)
        self.assertEqual(state['phase'],'guided_practice')
        self.assertIsNone(current_task(state))
        self.assertEqual(state['teaching_tasks'][0]['status'],'completed')
        self.assertFalse(state['completed'])

    def test_pending_lecture_cannot_be_skipped(self):
        with patch('backend.lecturer.configured', return_value=True):
            state = self.prepare()
        with self.assertRaises(ValueError):
            apply_event(state,'finish_lecture',{})
        self.assertEqual(state['phase'],'lecture')

    def test_exam_lecture_counts_as_help_and_restores_task(self):
        with patch('backend.lecturer.configured', return_value=False):
            state = self.prepare()
            complete_lecture(state)
            state['phase'] = 'independent_assessment'
            before = state['matrix']
            apply_event(state,'request_teaching',{'topic':'swap'})
            self.assertTrue(state['helped'])
            complete_lecture(state)
            self.assertEqual(state['phase'],'independent_assessment')
            self.assertEqual(state['matrix'],before)

    def test_invalid_topic_and_duplicate_dispatch(self):
        with patch('backend.lecturer.configured', return_value=False):
            state = self.prepare()
            with self.assertRaises(ValueError):
                dispatch(state)
            complete_lecture(state)
            with self.assertRaises(ValueError):
                dispatch(state,'unknown')

    def test_model_receives_task_not_credentials(self):
        with patch('backend.lecturer.configured', return_value=False):
            state = self.prepare()
        state['token'] = 'private-credential'
        with patch('backend.lecturer.complete', return_value='讲解') as model:
            self.assertEqual(remote_lecture(current_task(state),state),'讲解')
            system, data = model.call_args.args
            self.assertIn('授课Agent',system)
            self.assertEqual(data['task']['topic'],'triangular_method')
            self.assertNotIn('private-credential',str(data))

    def test_old_messages_are_not_falsely_labelled(self):
        state = new_state()
        state['messages'].append({'id':'old','role':'teacher','text':'旧版本消息'})
        self.assertEqual(public_state(state)['messages'][-1]['agent'],'legacy')
