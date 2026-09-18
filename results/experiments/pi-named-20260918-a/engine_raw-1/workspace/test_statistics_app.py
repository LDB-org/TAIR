import unittest
import statistics_app


class TestSummarizeNumbers(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(statistics_app.summarize_numbers([]), {'count': 0, 'total': 0, 'min': None, 'max': None})

    def test_negatives(self):
        self.assertEqual(statistics_app.summarize_numbers([-5, -2, -10]), {'count': 3, 'total': -17, 'min': -10, 'max': -2})

    def test_duplicates(self):
        self.assertEqual(statistics_app.summarize_numbers([3, 3, 1, 3]), {'count': 4, 'total': 10, 'min': 1, 'max': 3})

    def test_fractional(self):
        self.assertEqual(statistics_app.summarize_numbers([0.5, -1.25, 2.75]), {'count': 3, 'total': 2.0, 'min': -1.25, 'max': 2.75})

    def test_input_preservation(self):
        values = [4, -2, 4, 0.5]
        original = list(values)
        result = statistics_app.summarize_numbers(values)
        self.assertEqual(values, original)
        self.assertEqual(result, {'count': 4, 'total': 6.5, 'min': -2, 'max': 4})


if __name__ == '__main__':
    unittest.main()
