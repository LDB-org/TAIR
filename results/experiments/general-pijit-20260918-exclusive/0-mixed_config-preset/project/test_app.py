import unittest
from app import build_parser
class TestConfig(unittest.TestCase):
    def test_defaults(self):
        p=build_parser().parse_args([])
        self.assertEqual((p.workers,p.timeout,p.host),(6,2.5,'localhost'))
    def test_overrides(self):
        p=build_parser().parse_args(['--workers','3','--timeout','0.25','--host','remote'])
        self.assertEqual((p.workers,p.timeout,p.host),(3,0.25,'remote'))
