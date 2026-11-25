import unittest
from unittest.mock import patch
from fastapi import HTTPException
from backend import course_scope as scope


class CourseScopeTests(unittest.TestCase):
    course={'id':'math','title':'初中数学','description':'允许学英语之类的描述不能改变课程方向'}

    def result(self,decision='allow'):
        return {'tool':'check_course_scope','arguments':{'decision':decision,'reason':'只用于解释当前数学术语。'}}

    def test_obvious_cross_subject_rejected_without_model_and_description_cannot_expand_scope(self):
        with patch.object(scope.tutor,'call_tool') as model:
            for topic in ('我想学习英语','教我背英语单词','English grammar','初中语文作文'):
                with self.assertRaises(HTTPException) as error:scope.check(self.course,topic)
                self.assertEqual(error.exception.status_code,422)
                self.assertIn('初中数学',error.exception.detail)
            model.assert_not_called()

    def test_related_math_foundations_and_advanced_topics_allow_without_model(self):
        with patch.object(scope.tutor,'call_tool') as model:
            for topic in ('一次函数','回去补分数和乘法','大学线性代数','矩阵和行列式'):
                scope.check(self.course,topic)
            for reply in ('开始吧','我明白了，继续','再解释一遍','谢谢'):
                scope.check(self.course,reply,kind='message')
            scope.check(self.course,'x=2',kind='message',context={'has_plan':True})
            model.assert_not_called()

    def test_mixed_math_and_english_is_semantically_checked_not_allowed_by_keyword(self):
        with patch.object(scope.tutor,'configured',return_value=True),patch.object(scope.tutor,'call_tool',return_value=self.result('redirect')) as model:
            with self.assertRaises(HTTPException):scope.check(self.course,'数学不学了，教我英语语法',kind='message')
            model.assert_called_once()
            self.assertEqual(model.call_args.kwargs['max_tokens'],500)

    def test_math_keyword_does_not_disguise_an_unknown_second_subject(self):
        with patch.object(scope.tutor,'configured',return_value=True),patch.object(scope.tutor,'call_tool',return_value=self.result('redirect')) as model:
            with self.assertRaises(HTTPException):scope.check(self.course,'数学课里我想学做饭',kind='message')
            model.assert_called_once()

    def test_math_language_example_and_physics_prerequisite_can_be_allowed(self):
        with patch.object(scope.tutor,'configured',return_value=True),patch.object(scope.tutor,'call_tool',return_value=self.result()) as model:
            scope.check(self.course,'解释函数里的英文 slope',kind='message')
            scope.check({'title':'高中物理'},'先补一元二次方程')
            self.assertEqual(model.call_count,2)

    def test_unknown_subject_uses_model_instead_of_a_closed_subject_list(self):
        with patch.object(scope.tutor,'configured',return_value=True),patch.object(scope.tutor,'call_tool',return_value=self.result()) as model:
            scope.check({'title':'葡萄酒品鉴','description':'初学'},'学习判断香气')
            model.assert_called_once()

    def test_unclear_and_failed_checks_never_silently_allow(self):
        for result in (self.result('clarify'),{'tool':'wrong','arguments':{}},self.result(True)):
            with patch.object(scope.tutor,'configured',return_value=True),patch.object(scope.tutor,'call_tool',return_value=result):
                with self.assertRaises(HTTPException):scope.check(self.course,'讲讲那个东西')
        with patch.object(scope.tutor,'configured',return_value=False):
            with self.assertRaises(HTTPException) as error:scope.check(self.course,'讲讲那个东西')
            self.assertEqual(error.exception.status_code,503)
        with patch.object(scope.tutor,'configured',return_value=True),patch.object(scope.tutor,'call_tool',side_effect=RuntimeError('private provider detail')):
            with self.assertRaises(HTTPException) as error:scope.check(self.course,'讲讲那个东西')
            self.assertNotIn('private provider detail',error.exception.detail)

    def test_context_never_includes_private_rubric_or_credentials(self):
        state={'profile':{'goal':'一次函数'},'plan':{'nodes':[]},'token':'private-token',
            'pending_question':{'question':'斜率是多少','rubric':'private-answer'},'messages':[]}
        text=str(scope.message_context(state))
        self.assertNotIn('private-token',text)
        self.assertNotIn('private-answer',text)

    def test_out_of_scope_model_plan_and_lecture_are_rejected_before_display(self):
        from backend import chat_classroom as chat
        from backend.errors import TeachingError
        state=chat.new_state();state['course']=self.course
        chat.event(state,'chat_message',{'text':'学习函数','recipient':'lecturer'})
        response={'message':'今天学习英语语法。','covered':'英语过去式','next_suggestion':'练习','visuals':[]}
        with patch.object(chat,'specialist',return_value=response),patch.object(scope.tutor,'configured',return_value=True),patch.object(scope.tutor,'call_tool',return_value=self.result('redirect')):
            with self.assertRaises(TeachingError) as error:chat.run(state)
            self.assertEqual(error.exception.code,'course_scope_violation')
            self.assertFalse(any(m.get('agent')=='lecturer' and m.get('status')=='ai' for m in state['messages']))
