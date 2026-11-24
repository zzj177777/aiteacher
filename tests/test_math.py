import random
import unittest
from fractions import Fraction
from backend.math_engine import number, matrix, strings, determinant, transform, triangular
from backend.content import PROBLEMS


class MathTests(unittest.TestCase):
    def test_exact_numbers(self):
        self.assertEqual(number('0.1') + number('0.2'), number('3/10'))
        self.assertEqual(number('-2/4'), Fraction(-1, 2))
        for value in ('1/0', '__import__("os")', '1e100', 'nan', '1/-2', '2**5', '9'*40):
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value)

    def test_invariant_random_paths(self):
        rng = random.Random(67)
        for _ in range(50):
            m = matrix([[rng.randint(-5, 5) for _ in range(3)] for _ in range(3)])
            original, factor = determinant(m), Fraction(1)
            for _ in range(12):
                target, source = rng.sample(range(3), 2)
                kind = rng.choice(['add', 'swap', 'scale'])
                k = rng.choice(['-2', '1/2', '3', '-1'])
                m, factor = transform(m, factor, {'kind': kind, 'source': source, 'target': target, 'multiple': k})
                self.assertEqual(original, factor * determinant(m))

    def test_zero_scale_and_same_row_rejected(self):
        m = matrix(PROBLEMS[0]['matrix'])
        for op in ({'kind':'scale','target':0,'multiple':'0'}, {'kind':'add','target':1,'source':1,'multiple':'2'}, {'kind':'swap','target':4,'source':1}, []):
            with self.assertRaises(ValueError):
                transform(m, Fraction(1), op)

    def test_singular_and_fraction(self):
        self.assertEqual(determinant(matrix(PROBLEMS[-1]['matrix'])), 0)
        m = matrix([['1/2',0,1], [0,2,3], [0,0,'-3/4']])
        self.assertTrue(triangular(m))
        self.assertEqual(determinant(m), Fraction(-3,4))
        self.assertEqual(matrix(strings(m)), m)


if __name__ == '__main__':
    unittest.main()
