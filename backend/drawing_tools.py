"""Validated adapters for JSXGraph and Mermaid, not custom drawing engines."""
import math
import re
from uuid import uuid4

TOOLS={'draw_function':'JSXGraph','draw_riemann_sum':'JSXGraph','draw_diagram':'Mermaid','draw_mindmap':'Markmap'}
FUNCTIONS={'x','pi','e','sin','cos','tan','asin','acos','atan','sinh','cosh','tanh','exp','log','sqrt','abs'}


def schema():
    props={k:{'type':'string'} for k in ('title','caption','expression','diagram','markdown')}
    props['tool']={'type':'string','enum':list(TOOLS)}
    for key in ('x_min','x_max','y_min','y_max','a','b'): props[key]={'type':'number'}
    props['rectangles']={'type':'integer','minimum':2,'maximum':200}
    props['sampling']={'type':'string','enum':['left','right','middle']}
    return {'type':'array','maxItems':3,'items':{'type':'object','properties':props,'required':['tool','title','caption'],'additionalProperties':False}}


def validate(items):
    if not isinstance(items,list) or len(items)>3: raise ValueError('每次最多三张教学图。')
    result=[]
    for spec in items:
        if not isinstance(spec,dict) or spec.get('tool') not in TOOLS: raise ValueError('绘图工具无效。')
        name=spec['tool'];allowed={'tool','title','caption'}|({'markdown'} if name=='draw_mindmap' else {'diagram'} if name=='draw_diagram' else {'expression','x_min','x_max','y_min','y_max'}|({'rectangles','sampling','a','b'} if name=='draw_riemann_sum' else set()))
        if set(spec)-allowed: raise ValueError('绘图参数包含未知字段。')
        for key,limit in [('title',120),('caption',500)]:
            if not isinstance(spec.get(key),str) or not spec[key].strip() or len(spec[key])>limit: raise ValueError('绘图说明格式无效。')
        clean=dict(spec)
        if name=='draw_mindmap':
            markdown=spec.get('markdown')
            if not isinstance(markdown,str) or not 1<=len(markdown)<=6000: raise ValueError('思维导图内容无效。')
            if len(markdown.splitlines())>100: raise ValueError('思维导图节点过多。')
            if not re.match(r'^\s*# ',markdown): raise ValueError('思维导图需以一级标题开始。')
            if re.search(r'<|>|!\[|\]\s*\(|\]\s*\[|^\s*\[[^\]]+\]:|https?\s*:|javascript\s*:|data\s*:|<!--|^\s*---|```',markdown,re.I|re.M): raise ValueError('思维导图仅支持标题和列表，不支持HTML、链接、图片或配置。')
        elif name=='draw_diagram':
            code=spec.get('diagram')
            if not isinstance(code,str) or not 1<=len(code)<=3500: raise ValueError('流程图内容无效。')
            if not re.match(r'^\s*(flowchart\s+(?:TD|TB|BT|LR|RL)|graph\s+(?:TD|TB|BT|LR|RL)|sequenceDiagram|mindmap)\b',code): raise ValueError('暂支持流程图、时序图和思维导图。')
            if re.search(r'%%\{|^\s*---|\bclick\b|https?\s*:|javascript\s*:|data\s*:|<\s*[a-z!/]|\b(?:href|src)\s*=|\b(?:init|config)\s*:',code,re.I|re.M): raise ValueError('流程图不能包含外链、HTML或配置指令。')
        else:
            expr=spec.get('expression')
            if not isinstance(expr,str) or not 1<=len(expr)<=200 or not re.fullmatch(r'[a-zA-Z0-9_\s.+*/^(),-]+',expr): raise ValueError('函数表达式无效。')
            if any(word not in FUNCTIONS for word in re.findall(r'[A-Za-z_]+',expr)): raise ValueError('表达式包含不支持的函数或变量。')
            for key,default in [('x_min',-5),('x_max',5),('y_min',-2),('y_max',5)]:
                value=spec.get(key,default)
                if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>10000: raise ValueError('坐标范围无效。')
                clean[key]=value
            if not 0.000001<clean['x_max']-clean['x_min']<=10000 or not 0.000001<clean['y_max']-clean['y_min']<=10000: raise ValueError('坐标范围顺序无效。')
            if name=='draw_riemann_sum':
                for key in ('a','b'):
                    value=spec.get(key)
                    if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>10000: raise ValueError('黎曼和必须指定实际积分区间a和b。')
                if not clean['x_min']<=spec['a']<spec['b']<=clean['x_max']: raise ValueError('积分区间需递增并位于显示范围内。')
                count=spec.get('rectangles',8);sampling=spec.get('sampling','right')
                if type(count) is not int or not 2<=count<=200 or sampling not in ('left','right','middle'): raise ValueError('黎曼和参数无效。')
                clean.update(rectangles=count,sampling=sampling)
        clean.update(id=str(uuid4()),engine=TOOLS[name],status='validated')
        result.append(clean)
    return result
