import unittest
from math_utils import total


class TestTotal(unittest.TestCase):

    def test_empty_sequence(self):
        self.assertEqual(total([]), 0)

    def test_negative_and_mixed_numbers(self):
        self.assertEqual(total([-1, 2, -3, 4]), 2)
        self.assertEqual(total([-5, -2, -3]), -10)

    def test_input_not_mutated(self):
        values = [1, 2, 3, 4]
        original = list(values)
        total(values)
        self.assertEqual(values, original)


if __name__ == "__main__":
    unittest.main()
