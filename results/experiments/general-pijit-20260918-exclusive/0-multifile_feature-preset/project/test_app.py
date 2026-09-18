import unittest

from textutil import slugify


class SlugifyTest(unittest.TestCase):
    def test_lowercase_and_hyphenate(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(slugify("   \t\n"), "")


class CliTest(unittest.TestCase):
    def test_echo_without_slug(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "app.py", "Hello World"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "Hello World")

    def test_slug_mode(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "app.py", "--slug", "Hello World"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "hello-world")


if __name__ == "__main__":
    unittest.main()
