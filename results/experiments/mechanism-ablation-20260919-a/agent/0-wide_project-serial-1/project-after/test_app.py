import unittest
from app import unique_names
class TestNames(unittest.TestCase):
    def test_order(self):
        self.assertEqual(unique_names([' B ','a','b',' A ','']),['B','a'])
    def test_empty(self):
        self.assertEqual(unique_names([]),[])
