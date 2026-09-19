import unittest

from textutil import slugify

class SlugifyTest(unittest.TestCase):
    def test_lowercase_and_hyphens(self):
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_whitespace_only(self):
        self.assertEqual(slugify('   '), '')

    def test_empty(self):
        self.assertEqual(slugify(''), '')

class CliTest(unittest.TestCase):
    def test_echo_without_slug(self):
        import subprocess
        out = subprocess.check_output(['python', 'app.py', 'Hello World'])
        self.assertEqual(out.decode().strip(), 'Hello World')

    def test_slug_mode(self):
        import subprocess
        out = subprocess.check_output(['python', 'app.py', '--slug', 'Hello World'])
        self.assertEqual(out.decode().strip(), 'hello-world')

if __name__ == '__main__':
    unittest.main()
