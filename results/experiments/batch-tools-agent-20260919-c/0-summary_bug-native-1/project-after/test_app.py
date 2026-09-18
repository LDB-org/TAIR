import unittest
from app import summarize
class TestSummary(unittest.TestCase):
    def test_duplicates(self):
        self.assertEqual(summarize([2,2,5])['count'],3)
    def test_empty(self):
        self.assertEqual(summarize([]),{'count':0,'total':0,'mean':None,'min':None,'max':None})
    def test_negative_values(self):
        result = summarize([-3, -1, -2])
        self.assertEqual(result['count'], 3)
        self.assertEqual(result['total'], -6)
        self.assertEqual(result['mean'], -2)
        self.assertEqual(result['min'], -3)
        self.assertEqual(result['max'], -1)
    def test_negative_and_float_values(self):
        result = summarize([-1.5, 2.5, -0.5, 4.0])
        self.assertEqual(result['count'], 4)
        self.assertEqual(result['total'], 4.5)
        self.assertEqual(result['mean'], 1.125)
        self.assertEqual(result['min'], -1.5)
        self.assertEqual(result['max'], 4.0)
    def test_input_immutability(self):
        values = [3, 1, 2, 2, -1]
        original = list(values)
        summarize(values)
        self.assertEqual(values, original)
    def test_input_order_preserved(self):
        values = [5, 1, 3, 2, 4]
        original = list(values)
        summarize(values)
        self.assertEqual(values, original)
