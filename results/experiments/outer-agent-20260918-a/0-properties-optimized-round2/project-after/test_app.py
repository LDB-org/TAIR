import unittest
from app import build_parser
class TestConfig(unittest.TestCase):
    def test_defaults(self):
        p=build_parser()
        a=p.parse_args(['--workers','3'])
        self.assertEqual((a.workers,a.timeout,a.host,a.verbose),(3,2.5,'remote',True))
        self.assertIn('Worker count',p.format_help())
        with self.assertRaises(SystemExit): p.parse_args([])
    def test_overrides(self):
        a=build_parser().parse_args(['--workers','9','--timeout','0.25','--host','custom'])
        self.assertEqual((a.workers,a.timeout,a.host),(9,0.25,'custom'))
