import subprocess
import unittest
from unittest.mock import patch

from backend import math_speech as ms
from backend.digital_human import speech_chunks


class MathSpeechTests(unittest.TestCase):
    def setUp(self): ms.spoken_math_text.cache_clear()

    def test_all_english_letter_names_are_sent_as_english_not_chinese(self):
        for letter in 'abcdefghijklmnopqrstuvwxyz':
            self.assertEqual(ms.identifier(letter).strip(), letter.upper())
            self.assertEqual(ms.identifier(letter.upper()).strip(), '大写 ' + letter.upper())
        self.assertEqual(ms.spoken_math_text(r'$A+B=a+b$'), '大写 A 加 大写 B 等于 A 加 B')

    def test_linear_function_and_separate_variables(self):
        self.assertEqual(ms.spoken_math_text(r'$y=kx+b$'), 'Y 等于 K 乘 X 加 B')
        self.assertEqual(ms.spoken_math_text(r'$k\ne0$，$x$，$y$，$b$'), 'K 不等于0， X ， Y ， B')

    def test_powers_parentheses_sign_and_implicit_products(self):
        spoken = ms.spoken_math_text(r'$x^2+2x+1=(x+1)^2$')
        self.assertEqual(spoken, 'X 的平方加2乘 X 加1等于左括号 X 加1右括号的平方')
        self.assertEqual(ms.spoken_math_text(r'$y=-4x+7$'), 'Y 等于负4乘 X 加7')
        self.assertEqual(ms.spoken_math_text(r'$x^3$'), 'X 的立方')

    def test_fraction_order_root_and_nested_quadratic_formula(self):
        self.assertEqual(ms.spoken_math_text(r'$\frac{1}{2}$'), '2分之1')
        formula = ms.spoken_math_text(r'$x=\frac{-b\pm\sqrt{b^2-4ac}}{2a}$')
        self.assertIn('左括号2乘 A 右括号分之', formula)
        self.assertIn('负 B 正负根号， B 的平方减4乘 A 乘 C ，根号结束', formula)
        self.assertNotIn(ms.FALLBACK, formula)

    def test_matrix_retains_rows(self):
        spoken = ms.spoken_math_text(r'$\begin{pmatrix}1&2\\0&1\end{pmatrix}$')
        self.assertIn('第1行，1，2；第2行，0，1', spoken)

    def test_supported_delimiters_code_and_escaped_commands(self):
        self.assertEqual(ms.spoken_math_text(r'\(k>0\)'), 'K 大于0')
        self.assertEqual(ms.spoken_math_text(r'\[x^2\]'), 'X 的平方')
        self.assertEqual(ms.spoken_math_text(r'$\\frac{1}{2}$'), '2分之1')
        self.assertEqual(ms.spoken_math_text('```math\nx^2\n```'), 'X 的平方')
        self.assertEqual(ms.spoken_math_text('```python\nprint("hi")\n```'), '这里的代码请看板书')

    def test_parser_failure_is_explicit_and_never_changes_source(self):
        original = r'公式 $\notARealCommand{x}$。'
        self.assertIn(ms.FALLBACK, ms.spoken_math_text(original))
        self.assertEqual(original, r'公式 $\notARealCommand{x}$。')
        with patch.object(ms.subprocess, 'run', side_effect=subprocess.TimeoutExpired('node', 8)):
            self.assertIn(ms.FALLBACK, ms.spoken_math_text(r'超时 $x+123$'))

    def test_prose_and_chunk_limit_are_preserved(self):
        source = r'一次函数 $y=kx+b$。其中 $k\ne0$。' * 50
        chunks = speech_chunks(source)
        self.assertTrue(all(0 < len(chunk) <= 240 for chunk in chunks))
        self.assertNotIn('请看板书', ''.join(chunks))
        self.assertIn('Y 等于 K 乘 X 加 B', ''.join(chunks))


if __name__ == '__main__': unittest.main()
