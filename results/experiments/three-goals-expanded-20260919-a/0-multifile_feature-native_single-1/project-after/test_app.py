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
        self.assertEqual(app.main(['Hello World']), 'Hello World')

    def test_slug_mode_returns_slug(self):
        self.assertEqual(app.main(['--slug', 'Hello World']), 'hello-world')

    def test_slug_mode_whitespace_only(self):
        self.assertEqual(app.main(['--slug', '   ']), '')


if __name__ == '__main__':
    unittest.main()
