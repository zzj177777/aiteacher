import unittest
from backend.lesson import new_state, apply_event, public_state
from backend.math_engine import matrix, number, transform, strings, determinant
from backend.content import get_problem
from backend.lecturer import current_task
from backend.teaching_session import unit


def complete_lecture(state):
    task = current_task(state)
    while task['session']['segment_status'] != 'completed':
        s = task['session']
        check = unit(task)['checks'][s['variant']]
        apply_event(state, 'submit_teaching_check', {'task_id':task['id'], 'check_id':s['check_id'], 'answer':check['answer']})
        if s['segment_status'] == 'passed':
            apply_event(state, 'next_teaching_segment', {})
    apply_event(state, 'finish_lecture', {})


def enter_practice():
    s = new_state()
    for _ in range(3):
        apply_event(s, 'submit_diagnostic_answer', {'choice':0})
    complete_lecture(s)
    return s


def solve(state):
    for col in range(2):
        m = matrix(state['matrix'])
        if m[col][col] == 0:
            source = next((r for r in range(col+1,3) if m[r][col] != 0), None)
            if source is not None:
                submit_op(state, {'kind':'swap','target':col,'source':source})
        m = matrix(state['matrix'])
        if m[col][col] == 0:
            continue
        for row in range(col+1,3):
            m = matrix(state['matrix'])
            if m[row][col] != 0:
                submit_op(state, {'kind':'add','target':row,'source':col,'multiple':str(-m[row][col]/m[col][col])})
    answer = str(determinant(matrix(get_problem(state['problem_id'])['matrix'])))
    return apply_event(state, 'submit_final_answer', {'answer':answer})


def submit_op(state, op):
    expected, _ = transform(matrix(state['matrix']), number(state['factor']), op)
    return apply_event(state, 'submit_row_step', {'operation':op,'result':strings(expected)})


class LessonTests(unittest.TestCase):
    def test_full_independent_journey(self):
        state = enter_practice()
        solve(state)
        self.assertFalse(state['attempts'][-1]['independent'])
        apply_event(state,'continue',{})
        solve(state)
        self.assertTrue(state['attempts'][-1]['independent'])
        apply_event(state,'continue',{})
        solve(state)
        self.assertEqual(state['factor'],'-1')
        apply_event(state,'continue',{})
        self.assertEqual(state['phase'],'rule_check')
        apply_event(state,'submit_explanation',{'answers':[1,2],'note':'我理解换行变号。'})
        self.assertTrue(state['completed'])
        self.assertFalse(state['explanation']['note_evaluated'])
        self.assertEqual(public_state(state)['report']['diagnostic_score'],3)

    def test_wrong_step_preserves_matrix(self):
        state = enter_practice()
        before = matrix(state['matrix'])
        result = apply_event(state,'submit_row_step',{'operation':{'kind':'add','target':1,'source':0,'multiple':'-2'},'result':[[1,2,1],[0,1,2],[3,8,6]]})
        self.assertFalse(result['correct'])
        self.assertEqual(before, matrix(state['matrix']))
        self.assertEqual(len(state['steps']),0)
        self.assertEqual(len(state['mistakes']),1)

    def test_hint_requires_fresh_test(self):
        state = enter_practice(); solve(state); apply_event(state,'continue',{})
        first = state['problem_id']
        apply_event(state,'request_hint',{})
        solve(state)
        self.assertFalse(state['attempts'][-1]['independent'])
        self.assertNotIn('exam_regular',state['passed'])
        apply_event(state,'continue',{})
        self.assertNotEqual(first,state['problem_id'])
        self.assertFalse(state['helped'])

    def test_question_restores_task_and_requires_exam_consent(self):
        state = enter_practice(); solve(state); apply_event(state,'continue',{})
        before = state['matrix']
        result = apply_event(state,'ask_question',{'text':'为什么倍加不变？'})
        self.assertTrue(result['needs_assistance_confirmation'])
        self.assertFalse(state['helped'])
        apply_event(state,'ask_question',{'text':'为什么倍加不变？','accept_assistance':True})
        self.assertTrue(state['helped'])
        self.assertEqual(before,state['matrix'])

    def test_method_required(self):
        state = enter_practice()
        self.assertFalse(apply_event(state,'submit_final_answer',{'answer':'1'})['correct'])
        self.assertFalse(state['problem_done'])

    def test_wrong_rule_check_does_not_pass(self):
        state = enter_practice(); solve(state); apply_event(state,'continue',{}); solve(state); apply_event(state,'continue',{}); solve(state); apply_event(state,'continue',{})
        apply_event(state,'submit_explanation',{'answers':[0,2]})
        self.assertEqual(state['phase'],'rule_remedy')
        apply_event(state,'finish',{})
        self.assertFalse(state['completed'])

    def test_no_answer_key_in_diagnostic_snapshot(self):
        s = public_state(new_state())
        self.assertNotIn('answer',s['diagnostic'])
        self.assertNotIn('diagnostic_results',s)

    def test_exhausted_tests_never_reused(self):
        state = enter_practice(); solve(state); apply_event(state,'continue',{})
        for _ in range(3):
            apply_event(state,'request_hint',{}); solve(state); apply_event(state,'continue',{})
        self.assertEqual(state['phase'],'report')
        self.assertFalse(state['completed'])
        self.assertEqual(len(state['used']),len(set(state['used'])))


if __name__ == '__main__':
    unittest.main()
