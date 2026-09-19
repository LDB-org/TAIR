import tempfile
import unittest
from pathlib import Path

from file_io import read_text, write_text


class FileIOTest(unittest.TestCase):
    def test_unicode_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.txt"
            text = "héllo wörld \u00e9\u4e2d\u6587"
            write_text(p, text)
            self.assertEqual(read_text(p), text)

    def test_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.txt"
            write_text(p, "first")
            write_text(p, "second")
            self.assertEqual(read_text(p), "second")

    def test_append(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "data.txt"
            write_text(p, "first")
            write_text(p, "second", append=True)
            self.assertEqual(read_text(p), "firstsecond")

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "missing.txt"
            with self.assertRaises(FileNotFoundError):
                read_text(p)


if __name__ == "__main__":
    unittest.main()
