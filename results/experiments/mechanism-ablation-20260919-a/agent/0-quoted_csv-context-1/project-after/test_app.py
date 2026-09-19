import unittest
from app import parse_people
class TestCSV(unittest.TestCase):
    def test_comma(self):
        self.assertEqual(parse_people('name,age,active\n"Doe, Jane",31,yes\n'),[{'name':'Doe, Jane','age':31,'active':True}])
    def test_empty(self):
        self.assertEqual(parse_people('name,age,active\n'),[])
