import unittest
from app import moving_average
class TestAverage(unittest.TestCase):
    def test_windows(self):
        self.assertEqual(moving_average([1,2,3,4],2),[1.5,2.5,3.5])
    def test_empty(self):
        self.assertEqual(moving_average([],2),[])
    def test_invalid(self):
        with self.assertRaises(ValueError): moving_average([1],0)
