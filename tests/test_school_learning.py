import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from backend import chat_classroom as chat, school_learning as school
from backend.errors import TeachingError


def selected(stage='primary',subject='math'):
    return school.SchoolSelection(stage_id=stage,subject_id=subject).context()


def topics():
    return dict(message='选一个想学的方向。',choices=[dict(title=t,description='从容易懂的例子开始。') for t in ['分数的意义','乘法的含义','认识图形']])


def decision(action='plan',steps=None):
    return dict(message='先学分数的意义，确认后开始。',reason='从具体小知识点开始',goal='分数的意义',background='年级和基础未知',objective='分数的意义',
                action=action,steps=steps or ['分数的意义','用例子检查'],plan_update='keep')


class SchoolLearningTests(unittest.TestCase):
    def test_selection_pairs_and_server_labels(self):
        self.assertEqual(sum(len(ids) for ids in school.ALLOWED.values()),21)
        for stage,subjects in school.ALLOWED.items():
            for subject in subjects:
                value=selected(stage,subject)
                self.assertEqual(value['stage_label'],school.STAGES[stage])
                self.assertEqual(value['subject_label'],school.SUBJECTS[subject])
                self.assertEqual(set(value),{'stage_id','subject_id','stage_label','subject_label'})
        for value in [dict(stage_id='primary',subject_id='physics'),dict(stage_id='unknown',subject_id='math'),
                      dict(stage_id='primary',subject_id='math',grade='六年级'),dict(stage_id='primary',subject_id='math',stage_label='大学')]:
            with self.assertRaises(ValidationError):school.SchoolSelection(**value)

    def test_only_stage_and_subject_are_known_and_durable(self):
        state=chat.new_state(selected())
        self.assertIsNone(state['plan'])
        self.assertFalse(chat.public(state)['working'])
        self.assertEqual(state['profile']['goal'],'')
        self.assertIn('小学数学',state['messages'][0]['text'])
        restored=json.loads(json.dumps(state))
        restored['profile']['background']='之后聊天收集的信息'
        self.assertEqual(chat.context(restored)['school_context'],selected())
        self.assertEqual(school.scope(restored)['title'],'小学数学')

    def test_explicit_unknown_requests_choices_without_a_plan_or_teaching(self):
        state=chat.new_state(selected())
        chat.event(state,'chat_message',dict(text='我不知道学什么',recipient='lecturer'))
        self.assertEqual(state['job']['route'],'planner')
        self.assertEqual(state['job']['intent'],'school_topics')
        with patch.object(chat,'suggest_school_topics',return_value=topics()),patch.object(chat,'check_course_output'),patch.object(chat,'specialist') as specialist:
            chat.run(state)
            specialist.assert_not_called()
        self.assertEqual(len(state['topic_choices']),3)
        self.assertIsNone(state['plan'])
        self.assertEqual(state['profile']['goal'],'')
        self.assertIn('1. 分数的意义',chat.context(state)['dialogue'][-1]['text'])

    def test_choice_then_plan_then_confirm_teaches_and_old_choices_expire(self):
        state=chat.new_state(selected())
        chat.event(state,'chat_suggest_topics',{})
        with patch.object(chat,'suggest_school_topics',return_value=topics()),patch.object(chat,'check_course_output'):chat.run(state)
        choice=state['topic_choices'][0]
        before=len(state['messages'])
        with self.assertRaises(ValueError):chat.event(state,'chat_choose_topic',{'choice_id':'stale'})
        self.assertEqual(len(state['messages']),before)
        chat.event(state,'chat_choose_topic',{'choice_id':choice['id']})
        self.assertEqual(state['job']['intent'],'school_intake')
        self.assertEqual(state['topic_choices'],[])
        with patch.object(chat,'decide',return_value=decision()),patch.object(chat,'check_course_output'),patch.object(chat,'specialist') as specialist:
            chat.run(state);specialist.assert_not_called()
        self.assertEqual(state['plan']['goal'],'分数的意义')
        with self.assertRaises(ValueError):chat.event(state,'chat_choose_topic',{'choice_id':choice['id']})
        chat.event(state,'chat_message',{'text':'开始吧'})
        with patch.object(chat,'decide',return_value=decision('teach')),patch.object(chat,'check_course_output'),patch.object(chat,'specialist',return_value=dict(message='平均分成几份。',covered='分数',next_suggestion='举例',visuals=[])):
            chat.run(state)
        self.assertTrue(any(m['agent']=='lecturer' and m.get('status')=='ai' for m in state['messages']))
        self.assertEqual(chat.context(state)['school_context'],selected())

    def test_specific_difficulty_is_not_mistaken_for_indecision(self):
        state=chat.new_state(selected('junior'))
        chat.event(state,'chat_message',{'text':'不知道怎么解一元二次方程'})
        self.assertEqual(state['job']['intent'],'school_intake')
        with patch.object(chat,'call_tool',return_value=dict(tool='arrange_learning',arguments=decision())) as model:
            chat.decide(state,dict(intent='school_intake'))
        self.assertEqual(model.call_args.args[1]['classroom']['school_context'],selected('junior'))
        self.assertIn('school_intake',model.call_args.args[0])

    def test_first_school_turn_cannot_skip_plan_or_make_a_whole_course(self):
        for result in [decision('teach'),decision(steps=['一','二','三','四','五'])]:
            state=chat.new_state(selected())
            chat.event(state,'chat_message',{'text':'想学分数'})
            with patch.object(chat,'decide',return_value=result),patch.object(chat,'check_course_output'),patch.object(chat,'specialist') as specialist:
                with self.assertRaises(TeachingError):chat.run(state)
                specialist.assert_not_called()
            self.assertIsNone(state['plan'])

    def test_bad_suggestions_are_not_published(self):
        for choices in [[dict(title='同一个',description='说明')]*3,[dict(title='缺说明')]*3,[],[dict(title='a',description='b')]*5]:
            state=chat.new_state(selected())
            with patch.object(chat,'call_tool',return_value=dict(tool='suggest_learning_topics',arguments=dict(message='选择',choices=choices))):
                with self.assertRaises(TeachingError):chat.suggest_school_topics(state)
        state=chat.new_state(selected())
        chat.event(state,'chat_suggest_topics',{})
        with patch.object(chat,'suggest_school_topics',return_value=topics()),patch('backend.course_scope.check',side_effect=HTTPException(422,'跨科')):
            with self.assertRaises(TeachingError):chat.run(state)
        self.assertEqual(state['topic_choices'],[])

    def test_ordinary_sessions_cannot_use_school_actions(self):
        for event in ['chat_suggest_topics','chat_choose_topic']:
            with self.assertRaises(ValueError):chat.event(chat.new_state(),event,{})
        with self.assertRaises(ValueError):chat.event(chat.new_state(selected()),'chat_intake',{})


if __name__=='__main__':unittest.main()
