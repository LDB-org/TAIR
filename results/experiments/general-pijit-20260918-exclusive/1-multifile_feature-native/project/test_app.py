import os
import subprocess
import sys
import unittest

from textutil import slugify


class SlugifyTest(unittest.TestCase):
    def test_lowercases_and_joins_words(self):
        self.assertEqual(slugify('  Hello   WORLD '), 'hello-world')

    def test_splits_on_any_whitespace(self):
        self.assertEqual(slugify('A\tB\nC'), 'a-b-c')

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(slugify('   '), '')

    def test_non_whitespace_characters_preserved(self):
        self.assertEqual(slugify('Keep_This'), 'keep_this')


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, 'app.py', *args],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_echo_without_slug(self):
        r = self.run_cli('  Hello World  ')
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, '  Hello World  \n')

    def test_slug_with_flag(self):
        r = self.run_cli('--slug', '  Hello World  ')
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, 'hello-world\n')


if __name__ == '__main__':
    unittest.main()
