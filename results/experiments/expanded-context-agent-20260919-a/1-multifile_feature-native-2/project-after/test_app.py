import unittest

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
    def test_echo_mode_preserves_original_text(self):
        self.assertEqual(app.slugify, slugify)  # sanity: module wired up
        # Echo behavior is the default (no --slug).
        # We exercise the CLI via subprocess to verify output.
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, 'app.py', 'Hello World'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, 'Hello World\n')

    def test_slug_mode(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, 'app.py', '--slug', 'Hello World'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, 'hello-world\n')

    def test_slug_mode_whitespace_only(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, 'app.py', '--slug', '   '],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '\n')


if __name__ == '__main__':
    unittest.main()
