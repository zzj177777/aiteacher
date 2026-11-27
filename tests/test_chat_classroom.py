import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend import chat_classroom as chat, app as server


def decision(action='teach', goal='学习积分'):
    return dict(message='我们先从一个小要点开始。',reason='根据学生目标和反馈。',goal=goal,background='学生自述会导数',objective='理解定积分的累积意义',action=action,steps=['理解累积','用例子检查'],plan_update='keep')


class ChatTests(unittest.TestCase):
    def state(self, text='我想学积分', recipient='auto'):
        state=chat.new_state();chat.event(state,'chat_message',dict(text=text,recipient=recipient));return state

    def test_arbitrary_subject_plan_and_lecture_handoff(self):
        state=self.state()
        result=dict(message='积分可以描述累积量。',covered='定积分的意义',next_suggestion='用面积例子检查')
        with patch.object(chat,'decide',return_value=decision()),patch.object(chat,'specialist',return_value=result):chat.run(state)
        self.assertEqual(state['profile']['goal'],'学习积分')
        self.assertEqual(state['tasks'][0]['recipient'],'lecturer')
        self.assertEqual(state['tasks'][1]['recipient'],'planner')
        self.assertEqual(state['job']['status'],'completed')

    def test_structured_feedback_reaches_next_planner_without_private_rubric(self):
        state=self.state()
        result=dict(message='讲解正文',covered='讲过累积含义',next_suggestion='用新题检查')
        with patch.object(chat,'decide',return_value=decision()),patch.object(chat,'specialist',return_value=result):chat.run(state)
        feedback=chat.context(state)['handoffs'][-1]
        self.assertEqual(feedback['feedback']['covered'],'讲过累积含义')
        self.assertEqual(feedback['node_id'],chat.current_node(state)['id'])
        self.assertEqual(feedback['job_id'],state['job']['id'])
        chat.event(state,'chat_message',dict(text='下一步'))
        with patch.object(chat,'call_tool',return_value=dict(tool='arrange_learning',arguments=decision('ask'))) as model:
            chat.decide(state,'下一步')
        self.assertEqual(model.call_args.args[1]['classroom']['handoffs'][-1]['feedback']['next_suggestion'],'用新题检查')
        task=chat.handoff(state,'planner','assessment','检查理解','依据讲授反馈')
        self.assertIn(feedback['id'],task['consumed_feedback_ids'])
        chat.handoff(state,'assessment','planner','目标','观察',{'rubric':'private-standard','verdict':'partial','observation':'证据','next_suggestion':'补讲'})
        self.assertNotIn('private-standard',json.dumps(chat.context(state)['handoffs']))
        self.assertNotIn('private-standard',json.dumps(chat.public(state)))
        state['plan']['id']='new-plan'
        self.assertEqual(chat.context(state)['handoffs'],[])

    def test_feedback_reference_survives_first_plan_creation(self):
        state=self.state(recipient='lecturer')
        lecture=dict(message='讲解',covered='已讲内容',next_suggestion='检查')
        with patch.object(chat,'specialist',return_value=lecture):chat.run(state)
        feedback_id=state['tasks'][-1]['id']
        chat.event(state,'chat_message',dict(text='请检查'))
        question=dict(message='检查',question='题目',rubric='私有标准',objective='目标')
        with patch.object(chat,'decide',return_value=decision('assess')),patch.object(chat,'specialist',return_value=question):chat.run(state)
        self.assertIn(feedback_id,state['tasks'][-1]['consumed_feedback_ids'])

    def test_plan_waits_for_student(self):
        state=self.state('我想学英语写作')
        with patch.object(chat,'decide',return_value=decision('plan','英语写作')),patch.object(chat,'specialist') as specialist:
            chat.run(state);specialist.assert_not_called()
        self.assertIsNone(state['pending_question'])

    def test_question_rubric_hidden_until_answer(self):
        state=self.state()
        q=dict(message='试试这题',question='常数函数的导数是多少？',rubric='private_expected_answer_0',objective='检查导数基础')
        with patch.object(chat,'decide',return_value=decision('diagnose')),patch.object(chat,'specialist',return_value=q):chat.run(state)
        self.assertNotIn('private_expected_answer_0',json.dumps(chat.public(state)))
        chat.event(state,'chat_message',dict(text='0'))
        self.assertEqual(state['job']['route'],'assessment_answer')
        feedback=dict(message='本题回答正确',verdict='correct',observation='常数导数题答对',next_suggestion='继续积分')
        with patch.object(chat,'specialist',return_value=feedback),patch.object(chat,'decide',return_value=decision('ask')):chat.run(state)
        self.assertEqual(state['evidence'][0]['source'],'model_judgment')
        self.assertIsNone(state['pending_question'])

    def test_question_interruption_is_not_incorrect_answer(self):
        state=self.state()
        state['profile']['goal']='学习积分'
        state['pending_question']=dict(id='q',question='问题',rubric='标准',objective='目标')
        chat.event(state,'chat_message',dict(text='这个符号是什么意思？'))
        result=dict(message='先澄清你的疑问',verdict='not_answer',observation='学生在提问',next_suggestion='讲解符号')
        with patch.object(chat,'specialist',return_value=result),patch.object(chat,'decide',return_value=decision('ask')):chat.run(state)
        self.assertEqual(state['evidence'],[])
        self.assertIsNotNone(state['pending_question'])

    def test_explicit_planner_does_not_grade_new_goal(self):
        state=self.state();state['pending_question']=dict(id='q',question='问题',rubric='标准',objective='目标')
        chat.event(state,'chat_message',dict(text='改学Python',recipient='planner'))
        self.assertEqual(state['job']['route'],'planner')
        self.assertIsNone(state['pending_question'])
        with patch.object(chat,'decide',return_value=decision('plan','Python')),patch.object(chat,'specialist') as specialist:
            chat.run(state);specialist.assert_not_called()
        self.assertEqual(state['evidence'],[])

    def test_schema_rejects_invented_action_and_extra_fields(self):
        state=self.state();args=decision();args['action']='execute_code'
        with patch.object(chat,'call_tool',return_value=dict(tool='arrange_learning',arguments=args)):
            with self.assertRaises(ValueError):chat.decide(state,'start')
        args=decision();args['score']=100
        with patch.object(chat,'call_tool',return_value=dict(tool='arrange_learning',arguments=args)):
            with self.assertRaises(ValueError):chat.decide(state,'start')

    def test_superseded_job_end_and_recovery(self):
        state=self.state();old=state['job']['id']
        chat.event(state,'chat_message',dict(text='换一个话题'))
        self.assertNotEqual(old,state['job']['id'])
        self.assertEqual(sum(m.get('status')=='pending' for m in state['messages']),1)
        self.assertTrue(chat.recover(state));self.assertFalse(chat.public(state)['working'])
        chat.event(state,'chat_end',{})
        self.assertTrue(state['completed']);self.assertIsNotNone(state['report'])
        with self.assertRaises(ValueError):chat.event(state,'chat_message',dict(text='继续'))


class OutlineTests(unittest.TestCase):
    lecture=dict(message='一个清楚的讲解',covered='当前概念',next_suggestion='继续')

    def ready(self, delivered=True):
        state=chat.new_state()
        state['profile']['goal']='学习积分'
        state['plan']=dict(goal='学习积分',steps=['理解累积','矩形求和','极限含义'])
        chat.ensure_outline(state)
        chat.current_node(state)['delivered']=delivered
        return state

    def test_example_keeps_outline_and_node(self):
        state=self.ready();original=copy.deepcopy(state['plan'])
        chat.event(state,'chat_example',{})
        with patch.object(chat,'decide') as planner,patch.object(chat,'specialist',return_value=self.lecture) as lecturer:
            chat.run(state);planner.assert_not_called()
            self.assertIn('理解累积',lecturer.call_args.args[2])
        self.assertEqual(original,state['plan'])
        self.assertEqual(state['evidence'],[])

    def test_continue_moves_exactly_one_node_and_keeps_outline(self):
        state=self.ready();original=copy.deepcopy(state['plan']);chat.event(state,'chat_continue',{})
        change=decision();change.update(plan_update='replace',steps=['不应该重写'],message='错误地跳到第三节点',reason='错误地跳到第三节点')
        with patch.object(chat,'decide',return_value=change),patch.object(chat,'specialist',return_value=self.lecture) as specialist:
            chat.run(state)
            self.assertEqual(specialist.call_args.args[2],'矩形求和')
        self.assertEqual(state['plan']['id'],original['id'])
        self.assertEqual(state['plan']['steps'],original['steps'])
        self.assertEqual(state['plan']['nodes'][0]['completion_source'],'student_acknowledgement')
        self.assertEqual(chat.current_node(state)['title'],'矩形求和')
        self.assertEqual(state['evidence'],[])
        self.assertNotIn('错误地跳到第三节点',json.dumps(state['messages'],ensure_ascii=False))
        self.assertTrue(any('第 2 个节点' in m['text'] and '矩形求和' in m['text'] for m in state['messages']))

    def test_initial_continue_starts_first_node(self):
        state=self.ready(delivered=False);chat.event(state,'chat_continue',{})
        with patch.object(chat,'decide',return_value=decision()),patch.object(chat,'specialist',return_value=self.lecture):chat.run(state)
        self.assertEqual(chat.current_node(state)['title'],'理解累积')
        self.assertFalse(any(n['status']=='completed' for n in state['plan']['nodes']))

    def test_pending_assessment_blocks_continue_without_mutation(self):
        state=self.ready();state['pending_question']=dict(id='q',question='题目',rubric='答案',objective='检查')
        original=copy.deepcopy(state)
        with self.assertRaises(ValueError):chat.event(state,'chat_continue',{})
        self.assertEqual(state,original)

    def test_example_preserves_question_and_marks_assistance(self):
        state=self.ready();state['pending_question']=dict(id='q',question='题目',rubric='secret_answer',objective='检查')
        chat.event(state,'chat_example',{})
        with patch.object(chat,'specialist',return_value=self.lecture):chat.run(state)
        self.assertEqual(state['pending_question']['id'],'q')
        self.assertTrue(state['pending_question']['assisted'])
        self.assertNotIn('secret_answer',json.dumps(chat.public(state)))

    def test_examples_remove_private_rubric_from_lecturer_context(self):
        state=self.ready();state['pending_question']=dict(question='问题',rubric='secret_answer',objective='检查')
        chat.event(state,'chat_example',{})
        with patch.object(chat,'checked_call',return_value=self.lecture) as call:
            chat.specialist(state,'lecturer','举例')
        self.assertNotIn('secret_answer',json.dumps(call.call_args.args[1]))
        self.assertIn('不同情境',call.call_args.args[0])

    def test_normal_dialogue_preserves_original_outline(self):
        state=self.ready();original=copy.deepcopy(state['plan']);chat.event(state,'chat_message',{'text':'请再解释一下'})
        revised=decision();revised['steps']=['新的临时思路']
        with patch.object(chat,'decide',return_value=revised),patch.object(chat,'specialist',return_value=self.lecture):chat.run(state)
        self.assertEqual(original,state['plan'])

    def test_last_node_acknowledgement_finishes_outline_not_assessment(self):
        state=self.ready()
        for node in state['plan']['nodes'][:-1]:node['status']='completed'
        state['plan']['nodes'][-1].update(status='current',delivered=True)
        chat.event(state,'chat_continue',{})
        with patch.object(chat,'decide') as decide:chat.run(state);decide.assert_not_called()
        self.assertIsNone(chat.current_node(state))
        self.assertFalse(state['completed'])
        self.assertEqual(state['evidence'],[])


class ChatWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=patch.object(server,'DB_PATH',Path(self.temp.name)/'test.sqlite3');self.db.start()
        with server.connect() as db:
            db.executescript('CREATE TABLE sessions(id TEXT PRIMARY KEY,token_hash TEXT,state TEXT,created_at TEXT); CREATE TABLE events(session_id TEXT,event_key TEXT,kind TEXT,payload TEXT,response TEXT,created_at TEXT,PRIMARY KEY(session_id,event_key));')
            server.courses.initialize(db)
        self.state=chat.new_state();chat.event(self.state,'chat_message',dict(text='学习积分'))
        self.save(self.state)

    def tearDown(self):self.db.stop();self.temp.cleanup()
    def save(self,state):
        with server.connect() as db:db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)',('test','hash',json.dumps(state),'today'))
    def read(self):
        with server.connect() as db:return json.loads(db.execute('SELECT state FROM sessions').fetchone()['state'])

    def test_stale_worker_cannot_override_new_student_message(self):
        captured=copy.deepcopy(self.state)
        chat.event(self.state,'chat_message',dict(text='改学英语'));self.save(self.state)
        with patch.object(server,'configured',return_value=True),patch.object(chat,'run'):
            server.run_chat('test',captured['job']['id'],captured)
        self.assertEqual(self.read()['job']['text'],'改学英语')

    def test_failure_is_visible_without_fake_teaching(self):
        with patch.object(server,'configured',return_value=True),patch.object(chat,'run',side_effect=ValueError('invalid')):
            server.run_chat('test',self.state['job']['id'],self.state)
        result=self.read();self.assertEqual(result['job']['status'],'failed');self.assertEqual(result['evidence'],[])
        self.assertFalse(chat.public(result)['working'])

    def test_error_stage_and_agent_are_saved_without_partial_progress(self):
        from backend.errors import TeachingError
        with patch.object(server,'configured',return_value=True),patch.object(chat,'decide',return_value=decision()),patch.object(chat,'specialist',side_effect=TeachingError('tool_parse','arguments_json','工具参数不是有效JSON。')):
            server.run_chat('test',self.state['job']['id'],self.state)
        saved=self.read();error=saved['job']['error']
        self.assertEqual(error['agent'],'lecturer')
        self.assertEqual(error['stage'],'tool_parse')
        self.assertIsNone(saved['plan'])
        self.assertEqual(saved['messages'][-1]['error'],error)
        with server.connect() as db:
            event=json.loads(db.execute('SELECT response FROM events').fetchone()[0])
        self.assertEqual(event['error'],error)

    def test_unknown_error_does_not_leak_exception_text(self):
        with patch.object(server,'configured',return_value=True),patch.object(chat,'run',side_effect=RuntimeError('secret-key-private-prompt')):
            with self.assertLogs('backend.app',level='ERROR') as logs:
                server.run_chat('test',self.state['job']['id'],self.state)
        saved=self.read()
        self.assertNotIn('secret-key-private-prompt',json.dumps(saved))
        self.assertNotIn('secret-key-private-prompt',''.join(logs.output))
        self.assertEqual(saved['job']['error']['code'],'internal_error')

    def test_usage_endpoint_requires_same_session_credential(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):server.session_usage('test',token='wrong')
        with patch.object(server,'read_session',return_value=self.state),patch.object(server.usage,'summary',return_value={'call_count':2}) as summary:
            self.assertEqual(server.session_usage('test',token='valid')['call_count'],2)
            summary.assert_called_once_with('test')

    def test_successful_job_is_committed_once(self):
        with patch.object(server,'configured',return_value=True),patch.object(chat,'decide',return_value=decision('plan')):
            server.run_chat('test',self.state['job']['id'],self.state)
            first=self.read()
            server.run_chat('test',self.state['job']['id'],self.state)
        result=self.read()
        self.assertEqual(first,result)
        self.assertEqual(result['job']['status'],'completed')
        self.assertEqual(result['revision'],1)

    def test_selection_explanation_uses_source_without_mutating_classroom(self):
        original=copy.deepcopy(self.state)
        source=self.state['messages'][0]
        body=server.ExplainSelection(message_id=source['id'],text='教学安排')
        with patch.object(server,'read_session',return_value=self.state),patch.object(server,'configured',return_value=True),patch.object(server,'complete',return_value='结合目标规划学习步骤。') as model:
            result=server.explain_selection('test',body,token='token')
        self.assertEqual(result['text'],'结合目标规划学习步骤。')
        self.assertEqual(model.call_args.args[1]['source_passage'],source['text'])
        self.assertEqual(model.call_args.args[1]['selected_text'],'教学安排')
        self.assertEqual(self.state,original)
        self.assertEqual(self.read(),original)

    def test_selection_explanation_provider_failure_is_explicit(self):
        from fastapi import HTTPException
        source=self.state['messages'][0]
        body=server.ExplainSelection(message_id=source['id'],text='教学安排')
        with patch.object(server,'read_session',return_value=self.state),patch.object(server,'configured',return_value=True),patch.object(server,'complete',side_effect=RuntimeError('private provider details')):
            with self.assertRaises(HTTPException) as error:server.explain_selection('test',body,token='token')
        self.assertEqual(error.exception.status_code,502)
        self.assertNotIn('private provider details',error.exception.detail)

    def board_selection_fixture(self):
        self.state['messages'].append({'id':'visible-lecture','agent':'lecturer','status':'ai','text':'授课完整上下文。'})
        self.save(self.state)
        board={'id':'board','source_message_id':'visible-lecture','status':'completed','result':{'steps':[
            {'id':'main-step','title':'看系数','board':'系数表示每次变化多少。','narration':'先看相邻输入的差。','question':'系数是2时怎样变化？','rubric':'PRIVATE RUBRIC'},
            {'id':'future-step','title':'FUTURE CONTENT','board':'FUTURE CONTENT'}]}}
        detour={'id':'detour','status':'completed','result':{'intro':'先补一个词。','steps':[
            {'id':'detour-step','title':'什么是系数','board':'系数就是字母前面的乘数。','narration':'比如三倍里的三。'}]}}
        with server.connect() as db:
            db.execute('UPDATE sessions SET token_hash=? WHERE id=?',(server.hashlib.sha256(b'token').hexdigest(),'test'))
            db.executescript('CREATE TABLE digital_boards(session_id TEXT, id TEXT, record TEXT); CREATE TABLE digital_board_detours(session_id TEXT,board_id TEXT,id TEXT,record TEXT);')
            db.execute('INSERT INTO digital_boards VALUES(?,?,?)',('test','board',json.dumps(board)))
            db.execute('INSERT INTO digital_board_detours VALUES(?,?,?,?)',('test','board','detour',json.dumps(detour)))
        return board,detour

    def test_whiteboard_selection_explanation_reuses_endpoint_and_only_current_visible_context(self):
        self.board_selection_fixture(); original=copy.deepcopy(self.state)
        body=server.ExplainSelection(message_id='visible-lecture',text='系数',board_id='board',step_id='main-step')
        with patch.object(server,'configured',return_value=True),patch.object(server,'complete',return_value='系数是字母前面的乘数。') as model:
            result=server.explain_selection('test',body,token='token')
        self.assertEqual(result['text'],'系数是字母前面的乘数。')
        data=model.call_args.args[1]
        self.assertEqual(data['source_kind'],'whiteboard'); self.assertIn('每次变化多少',data['source_passage'])
        self.assertEqual(data['lecture_context'],'授课完整上下文。')
        self.assertNotIn('PRIVATE',json.dumps(data)); self.assertNotIn('FUTURE',json.dumps(data))
        self.assertEqual(self.read(),original)

    def test_detour_selection_explanation_has_actual_detour_not_main_board(self):
        self.board_selection_fixture(); original=copy.deepcopy(self.state)
        body=server.ExplainSelection(message_id='visible-lecture',text='乘数',board_id='board',step_id='detour-step',detour_id='detour')
        with patch.object(server,'configured',return_value=True),patch.object(server,'complete',return_value='相乘的那个数。') as model:
            server.explain_selection('test',body,token='token')
        data=model.call_args.args[1]
        self.assertEqual(data['source_kind'],'detour'); self.assertIn('字母前面的乘数',data['source_passage'])
        self.assertNotIn('每次变化多少',data['source_passage']); self.assertNotIn('PRIVATE',json.dumps(data))
        self.assertEqual(self.read(),original)

    def test_selection_context_rejects_cross_session_mismatched_source_and_stale_step(self):
        from fastapi import HTTPException
        self.board_selection_fixture(); source=self.state['messages'][0]['id']
        cases=[({'board_id':'missing','step_id':'main-step'},404),({'board_id':'board'},422),
               ({'board_id':'board','step_id':'stale'},404),({'board_id':'board','step_id':'detour-step','detour_id':'missing'},404),
               ({'message_id':source,'board_id':'board','step_id':'main-step'},422)]
        with patch.object(server,'complete') as model:
            for changes,code in cases:
                body=server.ExplainSelection(**{'message_id':'visible-lecture','text':'系数',**changes})
                with self.assertRaises(HTTPException) as error:server.explain_selection('test',body,token='token')
                self.assertEqual(error.exception.status_code,code)
            with server.connect() as db:
                with self.assertRaises(HTTPException) as error:server.digital_board.selection_context(db,'other-session','visible-lecture','board','main-step')
                self.assertEqual(error.exception.status_code,404)
            model.assert_not_called()
