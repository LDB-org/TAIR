import unittest
from textutil import slugify
import app

class TestSlugify(unittest.TestCase):
    def test_lowercase_and_hyphenate(self):
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_whitespace_only(self):
        self.assertEqual(slugify('   '), '')

class TestCLI(unittest.TestCase):
    def test_echo_mode(self):
        self.assertEqual(app.main(['Hello World']), None)

    def test_slug_mode(self):
        self.assertEqual(app.main(['--slug', 'Hello World']), None)

if __name__ == '__main__':
    unittest.main()
