import json
import subprocess
import sys
import unittest

from catalog import clean_names


class CleanNamesTest(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(clean_names([]), [])

    def test_whitespace_only_names(self):
        self.assertEqual(clean_names(['   ', '\t', '\n', '  \t  ']), [])

    def test_trim_names(self):
        self.assertEqual(clean_names(['  Ada  ', '\tBob\n', '  Grace ']), ['Ada', 'Bob', 'Grace'])

    def test_duplicates_after_trimming(self):
        self.assertEqual(clean_names([' Ada ', 'Ada', '  Ada  ', 'Bob', 'Bob']), ['Ada', 'Bob'])

    def test_preserves_first_occurrence_order(self):
        self.assertEqual(clean_names(['Bob', 'Ada', 'Bob', 'Ada', 'Grace']), ['Bob', 'Ada', 'Grace'])

    def test_unicode(self):
        self.assertEqual(clean_names(['  李雷  ', '李雷', ' 韩梅梅 ']), ['李雷', '韩梅梅'])

    def test_cli_output(self):
        result = subprocess.run(
            [sys.executable, 'catalog.py'],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), ['Ada', 'Bob'])


if __name__ == '__main__':
    unittest.main()
