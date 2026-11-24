"""Exact, bounded, code-free arithmetic for 3x3 determinant exercises."""
from fractions import Fraction
import re


def number(value):
    text = str(value).strip()
    if len(text) > 30 or not re.fullmatch(r"[+-]?\d+(?:/\d+|\.\d+)?", text):
        raise ValueError("请输入整数、分数（如 -1/2）或有限小数。")
    try:
        result = Fraction(text)
    except (ValueError, ZeroDivisionError):
        raise ValueError("分数的分母不能为零。")
    if abs(result.numerator) > 10**12 or result.denominator > 10**9:
        raise ValueError("数值过大，请检查输入。")
    return result


def matrix(values):
    if not isinstance(values, list) or len(values) != 3 or any(not isinstance(row, list) or len(row) != 3 for row in values):
        raise ValueError("需要一个 3 × 3 矩阵。")
    return [[number(v) for v in row] for row in values]


def strings(values):
    return [[str(v) for v in row] for row in values]


def determinant(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    return a * (e*i - f*h) - b * (d*i - f*g) + c * (d*h - e*g)


def triangular(m):
    return all(m[i][j] == 0 for i, j in [(1, 0), (2, 0), (2, 1)])


def transform(m, factor, operation):
    if not isinstance(operation, dict):
        raise ValueError("行操作格式无效。")
    kind = operation.get("kind")
    try:
        target = int(operation.get("target", -1))
        source = int(operation.get("source", -1))
    except (ValueError, TypeError):
        raise ValueError("请选择有效的行。")
    if target not in range(3):
        raise ValueError("目标行应为第 1 至 3 行。")
    out = [row[:] for row in m]
    if kind in ("add", "swap") and (source not in range(3) or source == target):
        raise ValueError("来源行和目标行必须不同。")
    if kind == "add":
        k = number(operation.get("multiple", ""))
        if k == 0:
            raise ValueError("请选择非零倍数，零倍加不会推进消元。")
        out[target] = [a + k*b for a, b in zip(m[target], m[source])]
    elif kind == "swap":
        out[target], out[source] = out[source], out[target]
        factor = -factor
    elif kind == "scale":
        k = number(operation.get("multiple", ""))
        if k == 0:
            raise ValueError("不能把一行乘以零，这会丢失原行列式的信息。")
        out[target] = [v*k for v in m[target]]
        factor /= k
    else:
        raise ValueError("不支持的行操作。")
    # Bound intermediate growth as well as input values.
    for row in strings(out):
        for value in row:
            number(value)
    number(str(factor))
    return out, factor


def next_hint(m):
    if triangular(m):
        return "已经是上三角形。将三个主对角线元素相乘，再乘左侧记录的系数 c，即得到原行列式。"
    for col in range(2):
        if m[col][col] == 0:
            candidate = next((r for r in range(col+1, 3) if m[r][col] != 0), None)
            if candidate is not None:
                return f"第 {col+1} 个主元为零。可以交换 R{col+1} 和 R{candidate+1}；记得行列式变号。"
            continue
        for row in range(col+1, 3):
            if m[row][col] != 0:
                k = -m[row][col] / m[col][col]
                return f"先消去第 {row+1} 行、第 {col+1} 列的 {m[row][col]}。可用 R{row+1} ← R{row+1} + ({k}) R{col+1}。请自己计算这一行的三个元素。"
    return "观察主对角线下方的元素，选择倍加或换行，逐步将它们消为零。"
