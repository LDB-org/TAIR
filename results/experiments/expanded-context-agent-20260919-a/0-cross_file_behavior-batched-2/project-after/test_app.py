import unittest
from app import render_users
class TestUsers(unittest.TestCase):
    def test_names(self):
        self.assertEqual(render_users([{'name':' Zoe '},{'name':'alice'},{'name':' '}]),'alice\nUnknown\nZoe')
    def test_empty(self):
        self.assertEqual(render_users([]),'')
