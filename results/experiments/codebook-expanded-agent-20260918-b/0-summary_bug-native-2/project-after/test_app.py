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
    def test_float_values(self):
        result = summarize([1.5, -2.5, 3.0])
        self.assertEqual(result['count'], 3)
        self.assertEqual(result['total'], 2.0)
        self.assertEqual(result['mean'], 2.0 / 3)
        self.assertEqual(result['min'], -2.5)
        self.assertEqual(result['max'], 3.0)
    def test_input_immutability(self):
        values = [3, 1, 2, 2]
        original = list(values)
        summarize(values)
        self.assertEqual(values, original)
    def test_duplicates_count_and_order(self):
        values = [5, 1, 5, 3, 1]
        result = summarize(values)
        self.assertEqual(result['count'], 5)
        self.assertEqual(result['total'], 15)
        self.assertEqual(result['mean'], 3)
        self.assertEqual(result['min'], 1)
        self.assertEqual(result['max'], 5)
