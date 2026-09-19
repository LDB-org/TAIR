import unittest
from app import summarize
class TestSummary(unittest.TestCase):
    def test_duplicates(self):
        self.assertEqual(summarize([2,2,5])['count'],3)
    def test_empty(self):
        self.assertEqual(summarize([]),{'count':0,'total':0,'mean':None,'min':None,'max':None})
    def test_negative(self):
        result = summarize([-3, -1.5, -3, 2])
        self.assertEqual(result['count'], 4)
        self.assertEqual(result['total'], -5.5)
        self.assertEqual(result['mean'], -1.375)
        self.assertEqual(result['min'], -3)
        self.assertEqual(result['max'], 2)
    def test_input_immutability(self):
        values = [3, 1, 2]
        original = list(values)
        summarize(values)
        self.assertEqual(values, original)
