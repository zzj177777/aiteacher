from copy import deepcopy
import json
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from backend import board_attention as attention, board_detours
from backend.errors import TeachingError
import test_digital_board as fixture


def context():
    return {'lecture': '向量必须非零，但特征值允许为零。', 'steps': [
        {'id': 'one', 'title': '先看定义', 'board': '🙂 条件 $x\\ne0$，条件 $x\\ne0$。', 'narration': '向量必须非零，但特征值允许为零。'},
        {'id': 'two', 'title': '普通说明', 'board': '这是一句普通说明。', 'narration': '没有额外提醒。'}]}


def mark(**changes):
    return {'quote': '$x\\ne0$', 'occurrence': 1, 'style': 'circle', 'kind': 'pitfall',
            'explanation': '不能把向量非零误认为特征值也必须非零。', 'evidence_quote': '向量必须非零，但特征值允许为零。', **changes}


def response(marks=None, **changes):
    return {'tool': 'annotate_teaching_board', 'arguments': {'steps': [{'step_id': 'one', 'marks': marks if marks is not None else [mark()]}]}, **changes}


class AttentionDesignTests(unittest.TestCase):
    def test_generated_explanation_has_no_character_cap(self):
        explanation = '完整保留解释与条件。' * 40
        result = attention.validate(response([mark(explanation=explanation)]), context())
        self.assertEqual(result['steps'][0]['marks'][0]['explanation'], explanation)

    def test_empty_plan_is_valid_and_no_keyword_or_first_formula_fallback(self):
        value = attention.validate({'tool': 'annotate_teaching_board', 'arguments': {'steps': []}}, context())
        self.assertEqual(value['steps'], [{'step_id': 'one', 'marks': []}, {'step_id': 'two', 'marks': []}])

    def test_occurrence_full_formula_and_utf16_offsets_are_exact(self):
        value = attention.validate(response([mark(occurrence=2, style='highlight')]), context())
        saved = value['steps'][0]['marks'][0]; text = context()['steps'][0]['board']
        start = text.rfind('$x\\ne0$')
        self.assertEqual(saved['start'], len(text[:start].encode('utf-16-le')) // 2)
        encoded = text.encode('utf-16-le')
        self.assertEqual(encoded[saved['start']*2:saved['end']*2].decode('utf-16-le'), saved['quote'])
        self.assertEqual(saved['style'], 'highlight')

    def test_invalid_grounding_partial_formula_and_overlap_fail_closed(self):
        cases = [([mark(quote='凭空生成的词')], 'attention_quote_mismatch'),
                 ([mark(quote='x\\ne0')], 'attention_partial_formula'),
                 ([mark(occurrence=3)], 'attention_occurrence'),
                 ([mark(evidence_quote='原文没有的知识')], 'attention_evidence_mismatch'),
                 ([mark(explanation='')], 'attention_explanation'),
                 ([mark(style='invented')], 'attention_mark_type'),
                 ([mark(), mark(kind='difficulty')], 'attention_overlap')]
        for marks, code in cases:
            with self.subTest(code=code), self.assertRaises(TeachingError) as error: attention.validate(response(marks), context())
            self.assertEqual(error.exception.code, code)
        raw = response(); raw['arguments']['steps'][0]['step_id'] = 'future-or-wrong'
        with self.assertRaises(TeachingError): attention.validate(raw, context())

    def test_analyzer_uses_separate_tool_call_with_no_private_grading_context(self):
        with patch.object(attention, 'call_tool', return_value={'tool':'annotate_teaching_board','arguments':{'steps':[]}}) as call:
            value = attention.analyze(context())
        self.assertEqual(value['steps'][0]['marks'], [])
        self.assertEqual(call.call_args.args[2][0]['function']['name'], 'annotate_teaching_board')
        self.assertNotIn('rubric', json.dumps(call.call_args.args[1]))


class AttentionApiTests(unittest.TestCase):
    setUp = fixture.BoardApiTests.setUp
    close = fixture.BoardApiTests.close
    call = fixture.BoardApiTests.call
    create = fixture.BoardApiTests.create
    detour = fixture.BoardApiTests.detour
    lesson = fixture.BoardApiTests.lesson

    def wait_for(self, path):
        for _ in range(80):
            code, value = self.call(path)
            if code != 200 or value['status'] != 'pending': return code, value
            time.sleep(.02)
        self.fail('attention job did not settle')

    def test_async_cache_authorization_and_dedup_without_teaching_changes(self):
        board = self.create(); path = f"/boards/{board['id']}/attention"; entered, release = threading.Event(), threading.Event(); captured = []
        def analyze(data):
            self.assertTrue(self.lock.acquire(blocking=False)); self.lock.release()
            captured.append(deepcopy(data)); entered.set(); release.wait(3)
            return {'steps': [{'step_id': s['id'], 'marks': []} for s in data['steps']]}
        with patch.object(attention, 'analyze', side_effect=analyze) as model:
            self.assertEqual(self.call(path, {}, token=None)[0], 401)
            self.assertEqual(self.call(path, {}, token='wrong')[0], 404)
            self.assertEqual(self.call(path)[0], 404)
            code, pending = self.call(path, {}); self.assertEqual(code, 202); self.assertTrue(entered.wait(1))
            self.assertEqual(self.call(path, {})[1]['id'], pending['id']); self.assertEqual(model.call_count, 1)
            release.set(); code, ready = self.wait_for(path)
            self.assertEqual(ready['status'], 'completed'); self.assertEqual(self.call(path, {})[1]['id'], pending['id'])
            self.assertEqual(model.call_count, 1)
        self.assertNotIn('PRIVATE', json.dumps(captured)); self.assertNotIn('rubric', json.dumps(captured))
        self.assertEqual(self.state, self.original); self.assertEqual(self.call('/boards/source/lecture')[1]['checks'], {})

    def test_failed_analysis_keeps_board_and_only_explicit_retry_calls_model(self):
        board = self.create(); path = f"/boards/{board['id']}/attention"
        with patch.object(attention, 'analyze', side_effect=TeachingError('attention_validation','attention_quote_mismatch','标记与原文不匹配。')) as model:
            self.call(path, {}); _, failed = self.wait_for(path)
            self.assertEqual(failed['status'], 'failed'); self.assertIsNone(failed['result'])
            self.assertEqual(self.call(path, {})[1]['id'], failed['id']); self.assertEqual(model.call_count, 1)
        with patch.object(attention, 'analyze', return_value={'steps': []}) as model:
            code, pending = self.call(path, {'retry': True}); self.assertEqual(code, 202)
            _, done = self.wait_for(path); self.assertEqual(done['status'], 'completed')
            self.assertNotEqual(done['id'], failed['id']); self.assertEqual(model.call_count, 1)
        self.assertEqual(self.call('/boards/source/lecture')[1]['status'], 'completed'); self.assertEqual(self.state, self.original)

    def test_detour_is_analyzed_separately_and_uses_saved_confusion(self):
        board = self.create(); base = f"/boards/{board['id']}"
        with patch.object(board_detours, 'teach', return_value=self.lesson()): detour = self.call(base+'/detours', self.detour(board))[1]
        with patch.object(attention, 'analyze', return_value={'steps': []}) as model:
            self.call(base+'/attention', {'detour_id': detour['id']}); _, done = self.wait_for(base+'/attention?detour_id='+detour['id'])
            data = model.call_args.args[0]
        self.assertEqual(done['status'], 'completed'); self.assertEqual(data['steps'][0]['id'], 'branch-step')
        self.assertEqual(data['student_confusion']['question'], self.detour(board)['question'])
        self.assertNotIn('PRIVATE', json.dumps(data)); self.assertEqual(self.call(base+'/attention')[0], 404)
        self.assertEqual(self.call(base+'/attention', {'detour_id': 'missing'})[0], 404)
        self.assertEqual(self.state, self.original)

    def test_changed_source_invalidates_old_cache_and_late_job_cannot_replace_new_plan(self):
        board = self.create(); path = f"/boards/{board['id']}/attention"; entered, release = threading.Event(), threading.Event(); calls = []
        def analyze(data):
            calls.append(deepcopy(data))
            if len(calls) == 1: entered.set(); release.wait(3)
            return {'steps': []}
        with patch.object(attention, 'analyze', side_effect=analyze):
            _, old = self.call(path, {}); self.assertTrue(entered.wait(1))
            with sqlite3.connect(self.path) as db:
                saved = json.loads(db.execute('SELECT record FROM digital_boards').fetchone()[0])
                saved['result']['steps'][0]['board'] += '新补充。'
                db.execute('UPDATE digital_boards SET record=?', (json.dumps(saved),))
            db.close()
            self.assertEqual(self.call(path)[0], 404)
            _, new = self.call(path, {}); self.assertNotEqual(old['id'], new['id'])
            _, done = self.wait_for(path); self.assertEqual(done['id'], new['id'])
            release.set()
        for _ in range(20):
            time.sleep(.01)
            self.assertEqual(self.call(path)[1]['id'], new['id'])
        self.assertEqual(self.state, self.original)
