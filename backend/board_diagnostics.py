"""Field-level board validation and safe, content-free failure records."""
import re

from .errors import TeachingError, diagnostic

# Generated teaching text has no per-field character cap. Keep this mapping for
# field names/legacy compatibility; validate meaning/structure instead of length.
TEXT_LIMITS = dict.fromkeys(('title', 'board', 'focus', 'narration', 'question', 'rubric', 'source_quote'))
FIELD_NAMES = {'title': '标题', 'board': '短板书', 'focus': '当前重点', 'narration': '讲解词',
               'question': '理解问题', 'rubric': '后台答案标准', 'source_quote': '原文依据',
               'visual_ids': '配图编号', 'steps': '板书步骤', 'feedback': '作答反馈', 'verdict': '判答结论'}


def invalid(code, message, field=None, step=None, **details):
    if field is not None: details['field'] = field
    if step is not None: details['step'] = step
    raise TeachingError('schema_validation', code, message, **details)


def label(field, step=None):
    return (f'第 {step} 步的' if step is not None else '') + FIELD_NAMES.get(field, '内容')


def checked_text(value, limit, field='text', step=None):
    name = label(field, step)
    if not isinstance(value, str):
        invalid('board_field_type', f'{name}应为文字，模型返回了其他类型。', field, step,
                expected_type='string', actual_type=type(value).__name__)
    value = value.strip()
    if not value:
        invalid('board_field_empty', f'{name}为空，需要重新整理。', field, step)
    if limit is not None and len(value) > limit:
        invalid('board_text_too_long', f'{name}有 {len(value)} 个字符，超过 {limit} 个字符的上限。',
                field, step, actual_length=len(value), limit=limit)
    return value


def fields(value, expected, field, step=None):
    if not isinstance(value, dict):
        invalid('board_object_type', f'{label(field, step)}应为结构化对象。', field, step)
    missing = sorted(expected - set(value))
    if missing:
        names = '、'.join(FIELD_NAMES.get(key, key) for key in missing)
        invalid('board_missing_fields', f'{label(field, step)}缺少必填字段：{names}。',
                field, step, missing_fields=missing)
    extra = len(set(value) - expected)
    if extra:
        # Never copy unknown field names or model values into public diagnostics.
        invalid('board_extra_fields', f'{label(field, step)}多出 {extra} 个不支持的字段。',
                field, step, extra_count=extra)


def reference_span(text, quote):
    """Only collapse whitespace; restore the *original* substring, including TeX.

    Keep a separating space, so commands such as ``\\sin x`` never match
    ``\\sinx``. No fuzzy matching, punctuation changes or semantic rewriting.
    """
    if quote in text: return quote
    tokens = list(re.finditer(r'\s+|\S', text))
    normalized = ''.join(' ' if m.group().isspace() else m.group() for m in tokens)
    target = re.sub(r'\s+', ' ', quote).strip()
    start = normalized.find(target)
    if start < 0 or not target: return None
    return text[tokens[start].start():tokens[start + len(target) - 1].end()]


def validate_board(response, source, *, presentation_only=False):
    if not isinstance(response, dict) or response.get('tool') != 'design_step_board':
        invalid('board_wrong_tool', '模型没有调用指定的板书编排工具。', 'tool')
    raw = response.get('arguments')
    fields(raw, {'title', 'steps'}, 'steps')
    if not isinstance(raw['steps'], list):
        invalid('board_steps_type', '板书步骤应为列表，模型返回了其他类型。', 'steps')
    if not 1 <= len(raw['steps']) <= 6:
        invalid('board_step_count', f'模型返回 {len(raw["steps"])} 步，要求为 1 至 6 步。',
                'steps', actual_count=len(raw['steps']), minimum=1, maximum=6)
    output = {'title': checked_text(raw['title'], None, 'title'), 'steps': []}
    known = {v['id'] for v in source.get('visuals', [])}
    assigned = set()
    from uuid import uuid4
    for number, item in enumerate(raw['steps'], 1):
        if presentation_only and isinstance(item,dict) and ({'question','rubric'} & set(item)):
            invalid('board_assessment_boundary', '板书编排不得生成题目或评分标准，请交给测评 Agent。', 'question', number)
        required = set(TEXT_LIMITS) - {'focus', 'question', 'rubric'}
        # Accept old records for repair/migration, never ask the new designer for these.
        legacy = {'question','rubric'} & set(item) if isinstance(item,dict) else set()
        required |= legacy
        fields({k: v for k, v in item.items() if k != 'focus'} if isinstance(item, dict) else item, required | {'visual_ids'}, 'steps', number)
        step = {key: checked_text(item[key], TEXT_LIMITS[key], key, number) for key in required}
        # Old records/tools may include focus. New generation no longer requests it.
        step['focus'] = checked_text(item['focus'], None, 'focus', number) if item.get('focus') else ''
        for field, parent in [('focus', step['board']), ('source_quote', source['text'])]:
            if field == 'focus' and not step[field]: continue
            match = reference_span(parent, step[field])
            if match is None:
                message = (f'第 {number} 步的当前重点无法在该步板书中找到，文字或公式不一致。' if field == 'focus'
                           else f'第 {number} 步的原文依据无法在授课讲稿中找到，可能被改写、删字或改变了公式。')
                invalid('board_focus_mismatch' if field == 'focus' else 'board_source_quote_mismatch',
                        message, field, number, match_policy='exact_or_whitespace_only')
            # Store source spelling so existing source-offset highlighting stays exact.
            step[field] = checked_text(match, TEXT_LIMITS[field], field, number)
        ids = item['visual_ids']
        if not isinstance(ids, list):
            invalid('board_visual_type', f'第 {number} 步的配图编号应为列表。', 'visual_ids', number)
        if len(ids) > 3:
            invalid('board_visual_count', f'第 {number} 步引用 {len(ids)} 张图，最多允许 3 张。',
                    'visual_ids', number, actual_count=len(ids), limit=3)
        unknown = sum(not isinstance(v, str) or v not in known for v in ids)
        if unknown:
            invalid('board_visual_unknown', f'第 {number} 步引用了 {unknown} 个不存在或无效的配图编号。',
                    'visual_ids', number, unknown_count=unknown, available_count=len(known))
        step.update(id=str(uuid4()), visual_ids=list(dict.fromkeys(ids)))
        assigned.update(ids); output['steps'].append(step)
    output['steps'][-1]['visual_ids'].extend(sorted(known - assigned))
    return output


def failure(exc, incident_id, agent='board_designer'):
    result = diagnostic(exc, agent, incident_id)
    if result['code'] == 'internal_error':
        result.update(stage='board_processing', message=('本步判答' if agent == 'board_check' else '板书') + '内部处理异常，详细诊断编号已记录。')
    return result


def legacy_failure(incident_id):
    return {'id': incident_id, 'agent': 'board_designer', 'stage': 'historical_record',
            'code': 'board_legacy_failure', 'message': '这条旧记录未保存具体失败字段；重新整理后会记录详细原因。',
            'details': {}}
