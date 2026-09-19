import unittest

from textutil import slugify
import app


class SlugifyTests(unittest.TestCase):
    def test_lowercases_and_joins_with_hyphens(self):
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_splits_on_whitespace(self):
        self.assertEqual(slugify('  Hello   World  '), 'hello-world')

    def test_whitespace_only_returns_empty_string(self):
        self.assertEqual(slugify('   '), '')

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(slugify(''), '')


class CliTests(unittest.TestCase):
    def test_echo_without_slug(self):
        self.assertEqual(app.main(['Hello World']), None)

    def test_slug_mode(self):
        self.assertEqual(app.main(['--slug', 'Hello World']), None)


if __name__ == '__main__':
    unittest.main()
