import io
import unittest
from contextlib import redirect_stdout

from textutil import slugify
import app


class SlugifyTests(unittest.TestCase):
    def test_lowercases_text(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_splits_on_whitespace_and_joins_with_hyphens(self):
        self.assertEqual(slugify("  Hello   World  "), "hello-world")

    def test_whitespace_only_returns_empty_string(self):
        self.assertEqual(slugify("   "), "")

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(slugify(""), "")


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            app.main()
        return buf.getvalue()

    def test_echo_mode_preserves_original_text(self):
        import sys
        sys.argv = ["app.py", "Hello World"]
        self.assertEqual(self.run_cli(sys.argv), "Hello World\n")

    def test_slug_mode_outputs_slug(self):
        import sys
        sys.argv = ["app.py", "--slug", "Hello World"]
        self.assertEqual(self.run_cli(sys.argv), "hello-world\n")


if __name__ == '__main__':
    unittest.main()
