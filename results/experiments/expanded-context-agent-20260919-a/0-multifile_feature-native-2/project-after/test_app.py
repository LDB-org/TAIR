import unittest
from unittest.mock import patch
from io import StringIO

from textutil import slugify
import app


class SlugifyTests(unittest.TestCase):
    def test_lowercases_and_joins_with_hyphens(self):
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_multiple_whitespace_collapses(self):
        self.assertEqual(slugify('  Hello   World  '), 'hello-world')

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(slugify('   '), '')
        self.assertEqual(slugify('\t\n'), '')

    def test_empty_string_returns_empty(self):
        self.assertEqual(slugify(''), '')

    def test_single_word(self):
        self.assertEqual(slugify('Hello'), 'hello')


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        with patch('sys.argv', ['app.py'] + argv), \
             patch('sys.stdout', new_callable=StringIO) as out:
            app.main()
            return out.getvalue()

    def test_echo_mode_preserves_original(self):
        self.assertEqual(self.run_cli(['Hello World']), 'Hello World\n')

    def test_slug_mode(self):
        self.assertEqual(self.run_cli(['--slug', 'Hello World']), 'hello-world\n')

    def test_slug_mode_whitespace_only(self):
        self.assertEqual(self.run_cli(['--slug', '   ']), '\n')


if __name__ == '__main__':
    unittest.main()
