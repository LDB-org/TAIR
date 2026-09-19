import tempfile,unittest
from pathlib import Path
from app import load_record
class TestRecords(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(load_record(Path(d)/'missing.json'))
    def test_bad_json(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text('{bad')
            with self.assertRaises(json.JSONDecodeError):load_record(p)
