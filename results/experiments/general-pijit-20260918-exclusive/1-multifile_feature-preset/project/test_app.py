import unittest

from textutil import slugify


class SlugifyTest(unittest.TestCase):
    def test_lowercases_and_joins_with_hyphens(self):
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_splits_on_whitespace(self):
        self.assertEqual(slugify('  Hello   World  '), 'hello-world')

    def test_whitespace_only_returns_empty_string(self):
        self.assertEqual(slugify('   '), '')

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(slugify(''), '')


class CliTest(unittest.TestCase):
    def test_echo_mode_preserves_original_text(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, 'app.py', 'Hello World'],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), 'Hello World')

    def test_slug_mode_outputs_slug(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, 'app.py', '--slug', 'Hello World'],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), 'hello-world')


if __name__ == '__main__':
    unittest.main()
