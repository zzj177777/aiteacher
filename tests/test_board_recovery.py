from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from backend import board_recovery as recovery, digital_board as board, board_detours as detours, usage
from backend.board_diagnostics import validate_board
from backend.errors import TeachingError
import test_digital_board as fixture


def plan(long=True):
    raw = fixture.designed()
    for step in raw['steps']: step.pop('focus', None)
    if long: raw['steps'][1]['board'] = '起点。' * 110 + '$x\\ne0$'
    return validate_board({'tool':'design_step_board','arguments':raw}, fixture.source())


def part(**changes):
    return {'title':'只看起点','board':'起点保留条件 $x\\ne0$。','narration':'现在看看常数项。','source_quote':'系数表示变化量。',**changes}


def invoke_repair(value, parts, index=1, max_steps=6):
    with patch.object(recovery, 'call_tool', return_value={'tool':'repair_board_step','arguments':{'steps':parts}}) as call:
        result = recovery.repair_step(value, index, {'issues':recovery.issues(value)}, 10,
            lecture=fixture.source()['text'], max_steps=max_steps,
            validate=lambda draft:validate_board({'tool':'design_step_board','arguments':draft},fixture.source()))
    return result,call


class RecoveryTests(unittest.TestCase):
    def test_short_plan_needs_one_call_and_no_repair(self):
        generate,repair=Mock(return_value=plan(False)),Mock()
        value,report=recovery.run(generate,repair)
        generate.assert_called_once();repair.assert_not_called()
        self.assertEqual(report['status'],'not_needed');self.assertEqual(report['repair_count'],0)

    def test_long_plan_repaired_locally_with_original_question_rubric_figures_and_ids(self):
        before=plan();after,call=invoke_repair(before,[part(board='先明确起点。'),part()])
        self.assertEqual(after['steps'][0],before['steps'][0])
        self.assertEqual(len(after['steps']),3)
        self.assertEqual(after['steps'][-1]['question'],before['steps'][-1]['question'])
        self.assertEqual(after['steps'][-1]['rubric'],before['steps'][-1]['rubric'])
        self.assertEqual(after['steps'][-1]['visual_ids'],before['steps'][-1]['visual_ids'])
        self.assertEqual(after['steps'][1]['visual_ids'],[])
        self.assertNotIn('PRIVATE',json.dumps(call.call_args.args[1]))
        generate,repair=Mock(return_value=before),Mock(return_value=after)
        result,report=recovery.run(generate,repair)
        self.assertEqual(result,after);self.assertEqual(report['repair_count'],1)
        self.assertEqual(report['status'],'repaired');generate.assert_called_once();repair.assert_called_once()

    def test_formula_deletion_rewriting_or_addition_and_bad_reference_are_rejected(self):
        for replacement in [part(board='忽略条件。'),part(board='$x=0$'),part(board='$x\\ne0$，并且 $y=2$')]:
            with self.assertRaises(TeachingError) as caught:invoke_repair(plan(),[replacement])
            self.assertEqual(caught.exception.code,'board_repair_formula_changed')
        with self.assertRaises(TeachingError) as caught:invoke_repair(plan(),[part(source_quote='编造的来源')])
        self.assertEqual(caught.exception.code,'board_source_quote_mismatch')

    def test_invalid_initial_output_gets_concrete_feedback_and_is_revalidated(self):
        error=TeachingError('schema_validation','board_missing_fields','缺少问题。',field='steps',step=2,missing_fields=['question'])
        generate=Mock(side_effect=[error,plan(False)]);repair=Mock()
        result,report=recovery.run(generate,repair)
        feedback=generate.call_args_list[1].args[0]
        self.assertEqual(feedback['issues'][0]['code'],'board_missing_fields')
        self.assertEqual(feedback['issues'][0]['step'],2)
        self.assertEqual(report['status'],'repaired');self.assertEqual(report['repair_count'],1)
        repair.assert_not_called()

    def test_two_repairs_only_and_best_valid_long_version_is_retained(self):
        original=plan();shorter=deepcopy(original);shorter['steps'][1]['board']='字'*310
        generate=Mock(return_value=original);repair=Mock(side_effect=[shorter,TeachingError('board_recovery','board_repair_formula_changed','公式被改变。')])
        value,report=recovery.run(generate,repair)
        self.assertEqual(value,shorter);self.assertEqual(len(value['steps'][1]['board']),310)
        self.assertEqual(report['status'],'long_fallback');self.assertEqual(report['repair_count'],2)
        self.assertEqual(len(report['attempts']),3);self.assertEqual(repair.call_count,2)

    def test_no_valid_plan_raises_after_two_repairs_with_safe_attempt_history(self):
        error=TeachingError('schema_validation','board_source_quote_mismatch','原文引用不匹配。',field='source_quote',step=1)
        generate=Mock(side_effect=error)
        with self.assertRaises(TeachingError) as caught:recovery.run(generate,Mock())
        self.assertEqual(generate.call_count,3);self.assertEqual(caught.exception.recovery['status'],'failed')
        self.assertEqual(caught.exception.recovery['repair_count'],2)

    def test_network_errors_are_not_blindly_retried_and_valid_board_survives(self):
        network=TeachingError('provider_request','timeout','请求超时。')
        generate=Mock(side_effect=network)
        with self.assertRaises(TeachingError):recovery.run(generate,Mock())
        generate.assert_called_once()
        original=plan();repair=Mock(side_effect=network)
        result,report=recovery.run(Mock(return_value=original),repair)
        self.assertEqual(result,original);self.assertEqual(report['status'],'long_fallback');self.assertEqual(repair.call_count,1)

    def test_time_budget_stops_extra_calls(self):
        clock=[0.0]
        def generate(*_):clock[0]=80.;return plan()
        repair=Mock()
        with patch.object(recovery.time,'monotonic',side_effect=lambda:clock[0]):
            value,report=recovery.run(generate,repair)
        repair.assert_not_called();self.assertEqual(report['stop_reason'],'time_budget')
        self.assertEqual(report['status'],'long_fallback')

    def test_split_cannot_exceed_existing_step_budget(self):
        with self.assertRaises(TeachingError) as caught:invoke_repair(plan(),[part(),part()],max_steps=2)
        self.assertEqual(caught.exception.code,'board_repair_structure')

    def test_detour_targeted_repair_keeps_original_return_transition(self):
        raw={'title':'补讲','intro':'先补一点。','return_transition':'回到原白板。','steps':[{'title':'先看条件','board':'字'*310+'$x\\ne0$','narration':'非零条件。'}]}
        value=detours.validate({'tool':'teach_board_detour','arguments':raw})
        response={'tool':'repair_board_step','arguments':{'steps':[{'title':'先看条件','board':'条件 $x\\ne0$。','narration':'非零条件。'}]}}
        with patch.object(recovery,'call_tool',return_value=response):
            result=recovery.repair_step(value,0,None,10,lecture='条件',max_steps=3,validate=lambda d:detours.validate({'tool':'teach_board_detour','arguments':d}))
        self.assertEqual(result['return_transition'],value['return_transition']);self.assertEqual(result['intro'],value['intro'])


class RecoveryApiTests(unittest.TestCase):
    setUp=fixture.BoardApiTests.setUp
    close=fixture.BoardApiTests.close
    call=fixture.BoardApiTests.call

    def test_recovery_is_cached_has_separate_usage_scope_and_does_not_change_main_state(self):
        raw=fixture.presentation();raw['steps'][1]['board']='起点。'*110
        scopes=[]
        def repair_model(*args,**kwargs):
            self.assertTrue(self.lock.acquire(blocking=False));self.lock.release()
            scopes.append(deepcopy(usage._scope.get()))
            return {'tool':'repair_board_step','arguments':{'steps':[part(board='常数项决定起点。')]}}
        with patch.object(board,'call_tool',return_value={'tool':'design_step_board','arguments':raw}) as initial,patch.object(recovery,'call_tool',side_effect=repair_model) as fix:
            code,value=self.call('/boards',{'message_id':'lecture'})
            self.assertEqual(code,200);self.assertEqual(value['status'],'completed');self.assertEqual(value['recovery']['status'],'repaired')
            cached=self.call('/boards',{'message_id':'lecture'})[1]
            self.assertEqual(cached['id'],value['id']);self.assertEqual(fix.call_count,1);self.assertEqual(initial.call_count,1)
        self.assertEqual(scopes[0]['agent'],'board_repair');self.assertEqual(scopes[0]['repair_attempt'],1)
        self.assertEqual(scopes[0]['job_id'],value['id']);self.assertNotIn('PRIVATE',json.dumps(value))
        history=self.call('/boards/source/lecture/diagnostics')[1]
        self.assertEqual(history['attempts'][0]['recovery']['repair_count'],1)
        self.assertEqual(self.state,self.original)

    def test_hard_failure_retains_original_and_diagnostic_after_bounded_repair(self):
        error=TeachingError('tool_parse','arguments_json','工具参数不是有效JSON。')
        with patch.object(board,'design',side_effect=error) as generate:
            _,value=self.call('/boards',{'message_id':'lecture'})
        self.assertEqual(generate.call_count,3);self.assertEqual(value['status'],'failed')
        self.assertEqual(value['diagnostic']['code'],'arguments_json');self.assertEqual(value['recovery']['repair_count'],2)
        self.assertEqual(self.state,self.original)
