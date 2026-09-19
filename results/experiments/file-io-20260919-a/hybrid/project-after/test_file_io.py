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
        p = self.dir / "u.txt"
        file_io.write_text(p, text)
        self.assertEqual(file_io.read_text(p), text)

    def test_overwrite(self):
        p = self.dir / "o.txt"
        file_io.write_text(p, "first")
        file_io.write_text(p, "second")
        self.assertEqual(file_io.read_text(p), "second")

    def test_append(self):
        p = self.dir / "a.txt"
        file_io.write_text(p, "one\n")
        file_io.write_text(p, "two\n", append=True)
        self.assertEqual(file_io.read_text(p), "one\ntwo\n")

    def test_empty_content(self):
        p = self.dir / "e.txt"
        file_io.write_text(p, "")
        self.assertEqual(file_io.read_text(p), "")

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            file_io.read_text(self.dir / "missing.txt")

    def test_accepts_pathlib_and_str(self):
        p = self.dir / "s.txt"
        file_io.write_text(str(p), "data")
        self.assertEqual(file_io.read_text(Path(p)), "data")


if __name__ == "__main__":
    unittest.main()
