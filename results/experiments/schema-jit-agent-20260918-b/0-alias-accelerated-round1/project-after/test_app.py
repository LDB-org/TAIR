import unittest
from app import build_parser
class TestAlias(unittest.TestCase):
    def test_alias(self):
        p=build_parser()
        self.assertEqual(p.parse_args(['-w','9']).workers,9)
        self.assertEqual(p.parse_args(['--workers','7']).workers,7)
        self.assertEqual(p.parse_args([]).workers,4)
