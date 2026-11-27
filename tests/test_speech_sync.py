import base64
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from backend import speech_sync as sync, digital_human as dh


class SpeechSyncTests(unittest.TestCase):
    def setUp(self):
        with sync._lock: sync._maps.clear()

    def test_browser_utf16_ranges_resolve_saved_source_only(self):
        board = '先看😀。\n再计算。'
        ranges = [sync.UnitRange(start=0, end=5), sync.UnitRange(start=6, end=10)]
        self.assertEqual(sync.checked_units(board, ranges), ['先看😀。', '再计算。'])
        for invalid in [[], [sync.UnitRange(start=6, end=10)], [sync.UnitRange(start=0, end=3)],
                        [sync.UnitRange(start=0, end=5), sync.UnitRange(start=4, end=10)]]:
            with self.subTest(ranges=invalid), self.assertRaises(HTTPException): sync.checked_units(board, invalid)

    def test_model_anchors_preserve_all_narration_without_guessing_times(self):
        narration = '先看横坐标。接下来算纵坐标。最后把两个数组成一个点。'
        groups = sync.validate_groups([
            {'first_unit': 0, 'last_unit': 0, 'start_quote': ''},
            {'first_unit': 1, 'last_unit': 2, 'start_quote': '接下来算纵坐标。'}], narration, 3)
        self.assertEqual(''.join(group['text'] for group in groups), narration)
        self.assertEqual(groups[1]['last_unit'], 2)
        invalids = [
            [{'first_unit': 0, 'last_unit': 0, 'start_quote': ''}],
            [{'first_unit': 1, 'last_unit': 2, 'start_quote': ''}],
            [{'first_unit': 0, 'last_unit': 0, 'start_quote': ''}, {'first_unit': 1, 'last_unit': 2, 'start_quote': '不存在'}],
        ]
        for raw in invalids:
            with self.subTest(raw=raw), self.assertRaises(ValueError): sync.validate_groups(raw, narration, 3)
        with self.assertRaises(ValueError):
            sync.validate_groups([{'first_unit': 0, 'last_unit': 0, 'start_quote': ''},
                                  {'first_unit': 1, 'last_unit': 1, 'start_quote': '重复'}], '开头重复，再次重复。', 2)

    def test_alignment_repairs_invalid_model_anchors_once(self):
        bad = {'tool': 'align_board_speech', 'arguments': {'groups': []}}
        good = {'tool': 'align_board_speech', 'arguments': {'groups': [
            {'first_unit': 0, 'last_unit': 0, 'start_quote': ''},
            {'first_unit': 1, 'last_unit': 1, 'start_quote': '再算。'}]}}
        with patch.object(sync, 'call_tool', side_effect=[bad, good]) as call:
            result = sync.align(['看横坐标。', '算纵坐标。'], '先看。再算。')
        self.assertEqual(call.call_count, 2)
        self.assertEqual(result[1]['text'], '再算。')
        self.assertIsNotNone(call.call_args.args[1]['validation_feedback'])

    def test_response_uses_actual_word_window_and_caches_only_semantic_map(self):
        board='先看。\n再算。';ranges=[sync.UnitRange(start=0,end=3),sync.UnitRange(start=4,end=7)]
        groups=sync.validate_groups([{'first_unit':0,'last_unit':0,'start_quote':''},
                                    {'first_unit':1,'last_unit':1,'start_quote':'再算。'}], '先看。再算。', 2)
        with patch.object(sync, 'align', return_value=groups) as align, patch.object(dh, 'speech_chunks', side_effect=lambda text:[text]), patch.object(dh, 'synthesize_timed', return_value={'audio':b'audio','words':[{'start':.3,'end':1.7}]}):
            first=sync.sync_response(board,'先看。再算。',ranges,0,'doubao-silang','fixture')
            second=sync.sync_response(board,'先看。再算。',ranges,1,'doubao-xionger','fixture')
        self.assertEqual(align.call_count,1)
        self.assertEqual(base64.b64decode(first['audio']),b'audio')
        self.assertEqual(first['chunks'],2)
        self.assertEqual(first['cue']['start'],.3)
        self.assertEqual(second['cue']['last_unit'],1)
        self.assertEqual(second['precision'],'timestamps')

    def test_failed_alignment_keeps_audio_without_inventing_board_cues(self):
        ranges=[sync.UnitRange(start=0,end=1),sync.UnitRange(start=2,end=3)]
        with patch.object(sync,'align',side_effect=ValueError('bad model')), patch.object(dh,'speech_chunks',return_value=['讲解']), patch.object(dh,'synthesize_timed',return_value={'audio':b'audio','words':[]}):
            packet=sync.sync_response('一\n二','讲解',ranges,0,'edge-xiaoxiao','fixture')
        self.assertFalse(packet['aligned'])
        self.assertIsNone(packet['cue'])
        self.assertEqual(packet['precision'],'segment')

    def test_ranges_validated_before_model_or_tts_and_audio_error_not_hidden(self):
        with patch.object(sync,'align') as align, self.assertRaises(HTTPException):
            sync.sync_response('板书', '讲解', [sync.UnitRange(start=0,end=99)],0,None,'fixture')
        align.assert_not_called()
        with patch.object(dh,'speech_chunks',return_value=['讲解']), patch.object(dh,'synthesize_timed',side_effect=HTTPException(502,'voice failed')), self.assertRaises(HTTPException):
            sync.sync_response('板书','讲解',[sync.UnitRange(start=0,end=2)],0,None,'fixture')


if __name__=='__main__':unittest.main()
