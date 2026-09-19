import tempfile
import unittest
from pathlib import Path

import file_io


class FileIOTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_unicode_round_trip(self):
        text = "héllo wörld \u4f60\u597d \U0001f600\nsecond line\n"
        path = self.dir / "u.txt"
        file_io.write_text(path, text)
        self.assertEqual(file_io.read_text(path), text)

    def test_overwrite(self):
        path = self.dir / "o.txt"
        file_io.write_text(path, "first")
        file_io.write_text(path, "second")
        self.assertEqual(file_io.read_text(path), "second")

    def test_append(self):
        path = self.dir / "a.txt"
        file_io.write_text(path, "one\n")
        file_io.write_text(path, "two\n", append=True)
        self.assertEqual(file_io.read_text(path), "one\ntwo\n")

    def test_empty_content(self):
        path = self.dir / "e.txt"
        file_io.write_text(path, "")
        self.assertEqual(file_io.read_text(path), "")

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            file_io.read_text(self.dir / "missing.txt")


if __name__ == "__main__":
    unittest.main()
