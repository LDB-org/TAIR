import unittest
from textutil import slugify
import app

class SlugifyTest(unittest.TestCase):
    def test_lowercase_and_hyphens(self):
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_whitespace_only(self):
        self.assertEqual(slugify('   '), '')

class CliTest(unittest.TestCase):
    def test_echo_without_slug(self):
        self.assertEqual(app.main(['Hello World']), 'Hello World')

    def test_slug_mode(self):
        self.assertEqual(app.main(['Hello World', '--slug']), 'hello-world')

if __name__ == '__main__':
    unittest.main()
