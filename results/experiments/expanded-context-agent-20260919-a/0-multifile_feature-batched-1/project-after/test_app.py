import unittest

from textutil import slugify

class SlugifyTest(unittest.TestCase):
    def test_lowercase_and_hyphenate(self):
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_whitespace_only(self):
        self.assertEqual(slugify('   '), '')

    def test_multiple_spaces(self):
        self.assertEqual(slugify('  foo   bar  '), 'foo-bar')

if __name__ == '__main__':
    unittest.main()
