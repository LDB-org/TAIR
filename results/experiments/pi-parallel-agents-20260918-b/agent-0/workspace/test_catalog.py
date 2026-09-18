import json
import unittest

from catalog import clean_names


class CleanNamesTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(clean_names([]), [])

    def test_whitespace_only_names_are_discarded(self):
        self.assertEqual(clean_names(['   ', '\t', '\n']), [])

    def test_duplicates_after_trimming_preserve_first_occurrence_order(self):
        self.assertEqual(clean_names([' Ada ', 'Ada', ' Bob ', 'Bob', 'Charlie']), ['Ada', 'Bob', 'Charlie'])

    def test_unicode_names(self):
        self.assertEqual(clean_names(['  José ', 'José', ' 東京 ', '東京']), ['José', '東京'])

    def test_cli_output_is_json(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, 'catalog.py'],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout), ['Ada', 'Bob'])


if __name__ == '__main__':
    unittest.main()
