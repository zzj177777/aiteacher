import unittest
from unittest.mock import patch
from backend import drawing_tools as drawing, chat_classroom as chat


class DrawingTests(unittest.TestCase):
    def plot(self, **extra):
        return dict(tool='draw_function',title='函数曲线',caption='观察变化',expression='sin(x)+x^2',**extra)

    def test_function_adapter_and_defaults(self):
        result=drawing.validate([self.plot()])[0]
        self.assertEqual(result['engine'],'JSXGraph');self.assertEqual(result['status'],'validated')
        self.assertEqual(result['x_min'],-5);self.assertTrue(result['id'])

    def test_riemann_adapter(self):
        spec=self.plot();spec.update(tool='draw_riemann_sum',a=0,b=1,x_min=-0.1,x_max=1.2,rectangles=4,sampling='right')
        result=drawing.validate([spec])[0]
        self.assertEqual(result['rectangles'],4);self.assertEqual(result['sampling'],'right')
        self.assertEqual((result['a'],result['b']),(0,1))

    def test_riemann_domain_cannot_be_missing_or_outside_view(self):
        for extra in ({},{'a':0,'b':20},{'a':1,'b':0},{'a':False,'b':1}):
            spec=self.plot();spec.update(tool='draw_riemann_sum',**extra)
            with self.subTest(extra=extra),self.assertRaises(ValueError):drawing.validate([spec])

    def test_mermaid_adapter(self):
        result=drawing.validate([dict(tool='draw_diagram',title='流程',caption='理解三步',diagram='flowchart LR\n A["细分"] --> B["求和"] --> C["取极限"]')])[0]
        self.assertEqual(result['engine'],'Mermaid')

    def test_reject_code_unknown_fields_and_invalid_bounds(self):
        for extra in ({'expression':'import(x)'},{'expression':'x.constructor'},{'expression':'x; alert(1)'},{'x_min':2,'x_max':1},{'y_max':float('nan')},{'x_min':True},{'code':'anything'}):
            spec=self.plot();spec.update(extra)
            with self.subTest(extra=extra),self.assertRaises(ValueError):drawing.validate([spec])

    def test_diagram_cannot_override_config_or_add_links(self):
        for code in ('flowchart LR\n click A "https://example.com"','flowchart LR\n A["<img src=x>"]','%%{init:{}}%%\n flowchart LR\n A-->B','flowchart LR\n A["https://example.com"]'):
            with self.subTest(code=code),self.assertRaises(ValueError):drawing.validate([dict(tool='draw_diagram',title='图',caption='说明',diagram=code)])

    def test_drawing_limits(self):
        with self.assertRaises(ValueError):drawing.validate([self.plot()]*4)
        spec=self.plot();spec.update(tool='draw_riemann_sum',rectangles=100000)
        with self.assertRaises(ValueError):drawing.validate([spec])

    def test_rejected_drawing_preserves_lecture(self):
        state=chat.new_state();chat.event(state,'chat_message',dict(text='画图讲解',recipient='lecturer'))
        result=dict(message='文字讲解仍在',covered='函数',next_suggestion='观察',visuals=[self.plot(code='invalid')])
        with patch.object(chat,'specialist',return_value=result):chat.run(state)
        lecture=next(m for m in state['messages'] if m.get('status')=='ai')
        self.assertEqual(lecture['text'],'文字讲解仍在');self.assertEqual(lecture['visuals'],[])
        self.assertTrue(lecture['visual_error']);self.assertEqual(state['job']['status'],'completed')

    def test_successful_tool_attaches_validated_spec_and_receipt(self):
        state=chat.new_state();chat.event(state,'chat_message',dict(text='画图讲解',recipient='lecturer'))
        result=dict(message='看这张图',covered='函数',next_suggestion='观察',visuals=[self.plot()])
        with patch.object(chat,'specialist',return_value=result):chat.run(state)
        lecture=next(m for m in state['messages'] if m.get('status')=='ai')
        self.assertEqual(lecture['visuals'][0]['engine'],'JSXGraph')
        self.assertTrue(any(m.get('to_agent')=='drawing' for m in state['messages']))

    def test_tool_schema_allows_empty_visuals_and_validates_structure(self):
        args=dict(message='文字',covered='概念',next_suggestion='继续',visuals=[],assessment_request={'objective':'检查概念','covered':'概念','prerequisites':'尚未确认','reason':'小节结束'})
        with patch.object(chat,'call_tool',return_value=dict(tool='submit_lecturer_result',arguments=args)):
            self.assertEqual(chat.specialist(chat.new_state(),'lecturer','讲概念')['visuals'],[])


class MindmapTests(unittest.TestCase):
    def test_mindmap_spec_round_trip(self):
        from backend import drawing_tools as drawing
        result=drawing.validate([dict(tool='draw_mindmap',title='学习框架',caption='先看全局',markdown='# 函数\n## 概念\n- 定义\n- 图像')])[0]
        self.assertEqual(result['engine'],'Markmap')
        self.assertIn('markdown',drawing.schema()['items']['properties'])

    def test_mindmap_rejects_active_content_and_unbounded_input(self):
        from backend import drawing_tools as drawing
        for markdown in ['# 标题\n<script>alert(1)</script>','# 标题\n[链接](https://example.test)','# 标题\n![图](x)','not a heading','# 标题\n'+'- 节点\n'*101]:
            with self.assertRaises(ValueError):drawing.validate([dict(tool='draw_mindmap',title='测试',caption='测试',markdown=markdown)])
