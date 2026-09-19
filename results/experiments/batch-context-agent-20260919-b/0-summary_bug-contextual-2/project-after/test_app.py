import unittest
from app import summarize
class TestSummary(unittest.TestCase):
    def test_duplicates(self):
        self.assertEqual(summarize([2,2,5])['count'],3)
    def test_negative(self):
        self.assertEqual(summarize([-1,-2,-3])['count'],3)
        self.assertEqual(summarize([-1,-2,-3])['total'],-6)
        self.assertEqual(summarize([-1,-2,-3])['mean'],-2)
        self.assertEqual(summarize([-1,-2,-3])['min'],-3)
        self.assertEqual(summarize([-1,-2,-3])['max'],-1)
    def test_float(self):
        self.assertEqual(summarize([1.5,2.5])['total'],4.0)
        self.assertEqual(summarize([1.5,2.5])['mean'],2.0)
    def test_input_immutability(self):
        values=[3,1,2]
        original=values[:]
        summarize(values)
        self.assertEqual(values,original)
    def test_empty(self):
        self.assertEqual(summarize([]),{'count':0,'total':0,'mean':None,'min':None,'max':None})
