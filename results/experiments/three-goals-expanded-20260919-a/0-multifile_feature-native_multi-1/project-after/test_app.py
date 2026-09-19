import io
import sys
import unittest
from contextlib import redirect_stdout

from textutil import slugify
import app


class SlugifyTests(unittest.TestCase):
    def test_lowercases_and_joins_with_hyphens(self):
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_multiple_words(self):
        self.assertEqual(slugify('The Quick Brown Fox'), 'the-quick-brown-fox')

    def test_whitespace_only_returns_empty_string(self):
        self.assertEqual(slugify('   '), '')
        self.assertEqual(slugify('\t\n  '), '')

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(slugify(''), '')

    def test_single_word(self):
        self.assertEqual(slugify('Hello'), 'hello')


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        """Run the CLI with the given argv and return captured stdout."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            app.main(argv)
        return buf.getvalue()

    def test_echo_mode_preserves_original_text(self):
        self.assertEqual(self.run_cli(['Hello World']), 'Hello World\n')

    def test_echo_mode_preserves_case_and_spacing(self):
        self.assertEqual(self.run_cli(['  Hello   World  ']), '  Hello   World  \n')

    def test_slug_mode(self):
        self.assertEqual(self.run_cli(['Hello World', '--slug']), 'hello-world\n')

    def test_slug_mode_whitespace_only(self):
        self.assertEqual(self.run_cli(['   ', '--slug']), '\n')


if __name__ == '__main__':
    unittest.main()
