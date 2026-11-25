"""Read common teaching mathematics from KaTeX's structural MathML output."""
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

FALLBACK = '这里有一个暂不支持朗读的公式，请结合板书查看'
WORDS = {'sin':'正弦','cos':'余弦','tan':'正切','cot':'余切','log':'对数','ln':'自然对数','lim':'极限','max':'最大值','min':'最小值','det':'行列式'}
SYMBOLS = {'+':'加','−':'减','-':'减','=':'等于','≠':'不等于','>':'大于','<':'小于','≥':'大于等于','≤':'小于等于',
           '×':'乘','⋅':'乘','·':'乘','÷':'除以','/':'除以','±':'正负','∓':'负正','≈':'约等于','∈':'属于','∉':'不属于',
           '∪':'并集','∩':'交集','⊂':'包含于','⊆':'包含于或等于','∞':'无穷大','→':'趋于','⇒':'推出','⇔':'等价于',
           '(':'左括号',')':'右括号','[':'左中括号',']':'右中括号','{':'左大括号','}':'右大括号','|':'竖线',
           ',':'，',';':'；',':':'比','!':'阶乘','%':'百分号','°':'度','∑':'求和','∏':'连乘','∫':'积分','∬':'二重积分',
           '∂':'偏导','∇':'纳布拉','′':'一阶导数','″':'二阶导数','…':'省略号','⋯':'省略号','⋮':'竖向省略号',
           'α':'阿尔法','β':'贝塔','γ':'伽马','δ':'德尔塔','ε':'艾普西龙','θ':'西塔','λ':'兰姆达','μ':'缪','π':'派',
           'ρ':'柔','σ':'西格玛','φ':'斐','ω':'欧米伽','Δ':'德尔塔','Σ':'西格玛','Ω':'欧米伽','∅':'空集',
           '\u2061':'','\u2062':'乘','\u2063':'，','\u200b':''}
TOKEN = re.compile(r'```[\s\S]*?```|`[^`\n]+`|\$\$[\s\S]+?\$\$|\\{1,2}\[[\s\S]+?\\{1,2}\]|\\{1,2}\([\s\S]+?\\{1,2}\)|(?<![\\$])\$(?!\$)[^$\n]+?(?<!\\)\$(?![\d$])')


def tag(node): return node.tag.rsplit('}', 1)[-1]


def identifier(text):
    if text in WORDS: return WORDS[text]
    if text in SYMBOLS: return SYMBOLS[text]
    # Give TTS an isolated English capital so it reads the letter name, not a
    # Chinese phonetic approximation or an English word/article. Case remains
    # explicit when the original mathematical symbol is uppercase.
    if re.fullmatch('[A-Za-z]', text): return ' ' + ('大写 ' if text.isupper() else '') + text.upper() + ' '
    if re.fullmatch(r'[0-9.]+|[\u4e00-\u9fff\s]+', text): return text
    raise ValueError('Unsupported mathematical identifier')


def read_node(node):
    name = tag(node)
    children = [n for n in node if tag(n) not in ('annotation', 'annotation-xml', 'mspace')]
    text = (node.text or '').strip()
    if name in ('annotation', 'annotation-xml', 'mspace'): return ''
    if name in ('mi', 'mn'): return identifier(text)
    if name == 'mtext': return text
    if name == 'mo':
        if text in SYMBOLS: return SYMBOLS[text]
        raise ValueError('Unsupported mathematical operator')
    if name == 'semantics': return read_node(children[0]) if children else ''
    if name == 'mfrac':
        numerator, denominator = children
        def grouped(n):
            spoken = read_node(n)
            return spoken if tag(n) in ('mi', 'mn', 'msup', 'msub') else '左括号' + spoken + '右括号'
        return grouped(denominator) + '分之' + grouped(numerator)
    if name == 'msqrt': return '根号，' + sequence(children) + '，根号结束'
    if name == 'mroot': return read_node(children[1]) + '次根号，' + read_node(children[0]) + '，根号结束'
    if name == 'msup':
        base, exponent = children
        power = ''.join(exponent.itertext())
        return read_node(base) + ('的平方' if power == '2' else '的立方' if power == '3' else '的' + read_node(exponent) + '次方')
    if name == 'msub': return read_node(children[0]) + '下标' + read_node(children[1])
    if name == 'msubsup':
        base, lower, upper = children
        if ''.join(base.itertext()) in ('∫','∑','∏'):
            return read_node(base) + '，下限为' + read_node(lower) + '，上限为' + read_node(upper) + '，'
        return read_node(base) + '下标' + read_node(lower) + '，上标' + read_node(upper) + '，'
    if name in ('munder', 'mover', 'munderover'):
        result = read_node(children[0])
        if name != 'mover': result += '，下方为' + read_node(children[1])
        if name != 'munder': result += '，上方为' + read_node(children[-1])
        return result + '，'
    if name == 'mtable':
        return '矩阵，' + '；'.join('第' + str(i+1) + '行，' + '，'.join(read_node(c) for c in row) for i, row in enumerate(children)) + '，矩阵结束'
    if name in ('math', 'span', 'mrow', 'mstyle', 'mpadded', 'mtd', 'mtr'):
        return sequence(children)
    # Invisible phantom layout is not mathematical content.
    if name == 'mphantom': return ''
    raise ValueError('Unsupported MathML structure')


def sequence(children):
    parts = []; previous_factor = False
    for child in children:
        name = tag(child); raw = ''.join(child.itertext()); spoken = read_node(child)
        if not spoken: continue
        factor = name in ('mi', 'mn', 'mfrac', 'msqrt', 'mroot', 'msup', 'msub', 'msubsup')
        # KaTeX attaches a parenthesized power to its closing fence, e.g. (x+1)^2.
        # That fence is not another factor after the preceding 1.
        scripted_closing = name in ('msup', 'msub', 'msubsup') and len(child) and tag(child[0]) == 'mo' and ''.join(child[0].itertext()) in (')', ']', '}')
        if scripted_closing: factor = False
        if previous_factor and factor: parts.append('乘')
        if name == 'mo' and raw in ('−', '-') and not previous_factor: spoken = '负'
        parts.append(spoken)
        previous_factor = factor or bool(scripted_closing) or (name == 'mo' and raw in (')', ']', '}'))
    return ''.join(parts)


def normalize_tex(tex):
    # Match the board's conservative normalization of a second escaping layer.
    for _ in range(2):
        runs = re.findall(r'\\+', tex)
        if not re.search(r'\\\\[A-Za-z]+', tex) or any(len(run) % 2 for run in runs): break
        tex = re.sub(r'\\+', lambda m: m[0][:len(m[0])//2], tex)
    return tex


@lru_cache(maxsize=128)
def spoken_math_text(source):
    matches = list(TOKEN.finditer(source))
    expressions, replacements = [], []
    for match in matches:
        token = match[0]; tex = None
        if token.startswith('```'):
            body = token[3:-3]; language, sep, content = body.partition('\n')
            if sep and language.strip().lower() in ('math', 'latex', 'tex'):
                tex = content.strip()
            else:
                replacements.append((match.start(), match.end(), '这里的代码请看板书')); continue
        elif token.startswith('`'):
            body = token[1:-1]
            if not re.fullmatch(r'[A-Za-z0-9+*/=^_().<>\-\s]+', body):
                replacements.append((match.start(), match.end(), '这里的内容请看板书')); continue
            tex = body
        else:
            for opening, closing in [('$$','$$'),('\\\\[','\\\\]'),('\\[','\\]'),('\\\\(','\\\\)'),('\\(','\\)'),('$','$')]:
                if token.startswith(opening) and token.endswith(closing): tex = token[len(opening):-len(closing)]; break
        expressions.append(normalize_tex(tex or ''))
        replacements.append((match.start(), match.end(), len(expressions)-1))
    readings = [FALLBACK] * len(expressions)
    if expressions:
        try:
            result = subprocess.run([os.environ.get('DIGITAL_HUMAN_NODE') or shutil.which('node') or 'node', str(Path(__file__).with_name('mathml_for_speech.cjs'))],
                input=json.dumps(expressions).encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            rendered = json.loads(result.stdout) if result.returncode == 0 else []
            for index, mathml in enumerate(rendered):
                if index >= len(readings) or not mathml: continue
                try: readings[index] = read_node(ET.fromstring(mathml)) or FALLBACK
                except (ValueError, ET.ParseError, RecursionError): pass
        except (OSError, subprocess.TimeoutExpired, ValueError): pass
    cursor, parts = 0, []
    for start, end, replacement in replacements:
        parts.extend([source[cursor:start], readings[replacement] if isinstance(replacement, int) else replacement]); cursor = end
    parts.append(source[cursor:])
    return re.sub(r' +', ' ', ''.join(parts)).strip()
