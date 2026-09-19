import unittest
from app import summarize
class TestSummary(unittest.TestCase):
    def test_duplicates(self):
        self.assertEqual(summarize([2,2,5])['count'],3)
    def test_empty(self):
        self.assertEqual(summarize([]),{'count':0,'total':0,'mean':None,'min':None,'max':None})
    def test_negative_values(self):
        result = summarize([-1, -2.5, 3])
        self.assertEqual(result['count'], 3)
        self.assertEqual(result['total'], -0.5)
        self.assertEqual(result['mean'], -0.5/3)
        self.assertEqual(result['min'], -2.5)
        self.assertEqual(result['max'], 3)
    def test_input_immutability(self):
        values = [3, 1, 2, 2]
        original = list(values)
        summarize(values)
        self.assertEqual(values, original)
