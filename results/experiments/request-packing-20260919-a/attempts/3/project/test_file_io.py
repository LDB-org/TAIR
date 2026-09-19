import tempfile
import unittest
from pathlib import Path

from file_io import read_text, write_text


class FileIOTest(unittest.TestCase):
    def test_unicode_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.txt"
            text = "héllo wörld \u00e9\u00fc\u4e2d\u6587"
            write_text(path, text)
            self.assertEqual(read_text(path), text)

    def test_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.txt"
            write_text(path, "first")
            write_text(path, "second")
            self.assertEqual(read_text(path), "second")

    def test_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.txt"
            write_text(path, "first")
            write_text(path, "second", append=True)
            self.assertEqual(read_text(path), "firstsecond")

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.txt"
            with self.assertRaises(FileNotFoundError):
                read_text(path)


if __name__ == "__main__":
    unittest.main()
