import unittest
from app import summarize
class TestSummary(unittest.TestCase):
    def test_duplicates(self):
        self.assertEqual(summarize([2,2,5])['count'],3)
    def test_empty(self):
        self.assertEqual(summarize([]),{'count':0,'total':0,'mean':None,'min':None,'max':None})
    def test_negative(self):
        self.assertEqual(summarize([-1,-2.5,3]),{'count':3,'total':-0.5,'mean':-0.5/3,'min':-2.5,'max':3})
    def test_input_immutability(self):
        values=[3,1,2]
        original=list(values)
        summarize(values)
        self.assertEqual(values,original)
