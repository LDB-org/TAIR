import unittest

from textutil import slugify

class SlugifyTest(unittest.TestCase):
    def test_lowercase_and_hyphenate(self):
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(slugify('   '), '')

    def test_multiple_words(self):
        self.assertEqual(slugify('Foo Bar Baz'), 'foo-bar-baz')

class CliTest(unittest.TestCase):
    def test_echo_without_slug(self):
        import subprocess, sys
        out = subprocess.check_output([sys.executable, 'app.py', 'Hello World'])
        self.assertEqual(out.decode().strip(), 'Hello World')

    def test_slug_mode(self):
        import subprocess, sys
        out = subprocess.check_output([sys.executable, 'app.py', 'Hello World', '--slug'])
        self.assertEqual(out.decode().strip(), 'hello-world')

if __name__ == '__main__':
    unittest.main()
