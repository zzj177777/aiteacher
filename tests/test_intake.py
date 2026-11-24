"""Initialization data stays self-reported, durable, and separate from evidence."""
import copy
import unittest
from unittest.mock import patch

from backend import chat_classroom as chat


def intake(**changes):
    return dict(topic='分数的意义',goals=['跟上课堂'],stage='小学',grade='三年级',
                background='不清楚分母的含义',time_budget='20 分钟',
                textbook='人教版',chapter='分数的初步认识',exam_scope='',exam_date='',**changes)


def plan(action='plan'):
    return dict(action=action,message='先从平均分开始，看看这个安排可以吗？',reason='根据目标与基础自述',
                goal='理解分数',background='学生自述不清楚分母含义',objective='理解平均分',
                steps=['理解平均分','认识分子和分母','做一道检查题'],plan_update='keep')


class IntakeTests(unittest.TestCase):
    def test_self_report_reaches_planner_and_does_not_create_mastery(self):
        state=chat.new_state()
        chat.event(state,'chat_intake',intake())
        self.assertEqual(state['job']['intent'],'intake')
        self.assertEqual(state['job']['route'],'planner')
        self.assertEqual(state['profile']['intake']['source'],'student_self_report')
        self.assertEqual(state['profile']['goal'],'分数的意义')
        self.assertIn('三年级',state['profile']['background'])
        self.assertEqual(state['evidence'],[])
        self.assertIn('分母',state['messages'][-2]['text'])
        with patch.object(chat,'call_tool',return_value={'tool':'arrange_learning','arguments':plan()}) as model,patch.object(chat,'specialist') as specialist:
            chat.run(state)
        args=model.call_args.args
        self.assertEqual(args[1]['trigger']['intent'],'intake')
        self.assertEqual(args[1]['classroom']['profile']['intake']['textbook'],'人教版')
        self.assertEqual(state['plan']['steps'],plan()['steps'])
        specialist.assert_not_called()
        self.assertEqual(state['evidence'],[])

    def test_bad_input_does_not_mutate_fresh_classroom(self):
        cases=[{'topic':'  '},{'goals':[]},{'goals':['随机目标']},{'goals':'入门理解'},
               {'stage':'未知'},{'grade':'高三'},{'background':None},{'topic':'字'*301},
               {'time_budget':'300 分钟'},{'source':'verified'}]
        for changes in cases:
            with self.subTest(changes=changes):
                state=chat.new_state();original=copy.deepcopy(state)
                data=intake();data.update(changes)
                with self.assertRaises(ValueError):chat.event(state,'chat_intake',data)
                self.assertEqual(state,original)

    def test_minimal_input_and_conditional_details(self):
        data={'topic':'Python','goals':['入门理解'],'stage':'自主学习','textbook':'旧选择','exam_scope':'旧范围','exam_date':'wrong'}
        normalized=chat.validate_intake(data)
        self.assertEqual(normalized['textbook'],'')
        self.assertEqual(normalized['exam_scope'],'')
        self.assertEqual(normalized['exam_date'],'')
        self.assertEqual(normalized['background'],'')
        data.update(goals=['备考提分'])
        with self.assertRaises(ValueError):chat.validate_intake(data)
        data.update(exam_date='2026-12-01')
        self.assertEqual(chat.validate_intake(data)['exam_date'],'2026-12-01')

    def test_initial_plan_requires_confirmation_before_specialist(self):
        state=chat.new_state();chat.event(state,'chat_intake',intake())
        with patch.object(chat,'decide',return_value=plan('teach')),patch.object(chat,'specialist') as specialist:
            with self.assertRaises(ValueError):chat.run(state)
        specialist.assert_not_called()
        self.assertIsNone(state['plan'])

    def test_old_sessions_and_chat_skip_remain_usable(self):
        state=chat.new_state();chat.event(state,'chat_message',{'text':'直接教我 Python'})
        self.assertNotIn('intake',state['profile'])
        self.assertEqual(state['job']['intent'],'message')
        original=copy.deepcopy(state)
        with self.assertRaises(ValueError):chat.event(state,'chat_intake',intake())
        self.assertEqual(state,original)

    def test_intake_not_lost_when_short_dialogue_window_rolls_over(self):
        state=chat.new_state();chat.event(state,'chat_intake',intake())
        for i in range(30):chat.message(state,'student',f'后续对话 {i}')
        data=chat.context(state)
        self.assertEqual(len(data['dialogue']),24)
        self.assertEqual(data['profile']['intake']['grade'],'三年级')


if __name__=='__main__':unittest.main()
