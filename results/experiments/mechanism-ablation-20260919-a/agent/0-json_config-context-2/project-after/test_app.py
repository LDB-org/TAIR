import unittest
from app import settings
class TestSettings(unittest.TestCase):
    def test_update(self):
        c=settings()
        self.assertEqual(c['server']['port'],9090)
        self.assertEqual(c['retry']['count'],4)
        self.assertEqual(c['features'],['metrics','tracing'])
