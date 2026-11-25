"""Validated school-entry context, independent of courses and textbook semesters."""
from pydantic import BaseModel, ConfigDict, Field, model_validator

STAGES={'primary':'小学','junior':'初中','senior':'高中'}
SUBJECTS={'chinese':'语文','math':'数学','english':'英语','physics':'物理','chemistry':'化学',
          'geography':'地理','biology':'生物学','ethics':'政治','politics':'政治','history':'历史'}
ALLOWED={
    'primary':{'chinese','math','english'},
    'junior':{'chinese','math','english','physics','chemistry','geography','biology','ethics','history'},
    'senior':{'chinese','math','english','physics','chemistry','geography','biology','politics','history'},
}


class SchoolSelection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    stage_id: str = Field(max_length=20)
    subject_id: str = Field(max_length=20)

    @model_validator(mode='after')
    def valid_pair(self):
        if self.stage_id not in ALLOWED or self.subject_id not in ALLOWED[self.stage_id]:
            raise ValueError('学段和科目组合无效，请重新选择科目入口。')
        return self

    def context(self):
        return {**self.model_dump(),'stage_label':STAGES[self.stage_id],'subject_label':SUBJECTS[self.subject_id]}


def scope(state):
    if state.get('course'):
        return state['course']
    selected=state.get('school_context')
    if not selected:
        return None
    return dict(id=f"school:{selected['stage_id']}:{selected['subject_id']}",
                title=selected['stage_label']+selected['subject_label'],
                description='自由小课，仅已知学段和科目；具体年级、教材、掌握程度均未知。')


def wants_suggestions(text):
    """Only explicit indecision, not '不知道怎么解方程' with a concrete topic."""
    if not isinstance(text,str):
        return False
    normalized=text.strip().rstrip('。！!？?，, ')
    return normalized in {'不知道','我不知道','没想好','我没想好','还没想好','不知道学什么',
                          '我不知道学什么','不知道想学什么','我还没想好学什么','给我几个选项',
                          '推荐几个学习方向','你给我推荐几个','帮我选个方向'}
