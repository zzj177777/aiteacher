"""Reviewed local question bank. Answers and rubrics never enter public snapshots."""
PROBLEMS = [
    {"id": "guided-01", "role": "guided", "title": "把三个位置变成零", "matrix": [[1,2,1],[2,5,3],[3,8,6]]},
    {"id": "guided-02", "role": "guided", "title": "再练一次倍加消元", "matrix": [[1,1,2],[2,3,5],[1,3,6]]},
    {"id": "practice-03", "role": "practice", "title": "负数也遵循同样的规则", "matrix": [[2,1,0],[4,3,1],[2,2,3]]},
    {"id": "practice-04", "role": "practice", "title": "分数倍的行操作", "matrix": [[2,1,1],[1,2,0],[3,1,2]]},
    {"id": "exam-01", "role": "exam_regular", "title": "独立挑战 · 完成三角化", "matrix": [[1,1,2],[2,3,5],[3,5,9]]},
    {"id": "exam-02", "role": "exam_regular", "title": "独立挑战 · 新的数字", "matrix": [[1,2,0],[2,5,1],[1,3,3]]},
    {"id": "exam-03", "role": "exam_regular", "title": "独立挑战 · 再试一题", "matrix": [[2,1,1],[4,3,2],[2,2,4]]},
    {"id": "swap-01", "role": "exam_swap", "title": "独立挑战 · 主元为零", "matrix": [[0,1,2],[1,2,1],[2,5,5]]},
    {"id": "swap-02", "role": "exam_swap", "title": "独立挑战 · 留意符号", "matrix": [[0,2,1],[1,1,0],[2,3,3]]},
    {"id": "singular-01", "role": "practice", "title": "遇到零行会怎样", "matrix": [[1,2,3],[2,4,6],[1,1,2]]},
]
DIAGNOSTICS = [
    {"id": "triangle", "question": "一个上三角形行列式的主对角线元素依次是 2、−1、3，它的值是多少？", "choices": ["−6", "4", "6"], "answer": 0, "concept": "triangle", "remedy": "上三角形行列式等于主对角线元素的乘积：2 × (−1) × 3 = −6。不是求和，也不取绝对值。"},
    {"id": "addition", "question": "执行 R₂ ← R₂ − 2R₁ 后，行列式的值如何变化？", "choices": ["不变", "乘以 −2", "变号"], "answer": 0, "concept": "addition", "remedy": "把一行的若干倍加到另一行，行列式值不变。倍数 −2 作用在被加进来的那一行，不是把整个目标行乘以 −2。"},
    {"id": "swap", "question": "交换两行后，如何从新行列式恢复原来的值？", "choices": ["乘以 −1", "不需要修正", "乘以 2"], "answer": 0, "concept": "swap", "remedy": "交换两行后行列式变号，因此原值 = −1 × 新值；交换两次则恢复原符号。"},
]


def get_problem(problem_id):
    return next(p for p in PROBLEMS if p["id"] == problem_id)


def choose(role, used):
    pool = [p for p in PROBLEMS if p["role"] == role]
    return next((p for p in pool if p["id"] not in used), None)
