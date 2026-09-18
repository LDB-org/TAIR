import unittest
import statistics_app


class SummarizeNumbersTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(
            statistics_app.summarize_numbers([]),
            {'count': 0, 'total': 0, 'min': None, 'max': None},
        )

    def test_negatives(self):
        self.assertEqual(
            statistics_app.summarize_numbers([-5, -1, -3]),
            {'count': 3, 'total': -9, 'min': -5, 'max': -1},
        )

    def test_duplicates(self):
        self.assertEqual(
            statistics_app.summarize_numbers([2, 2, 2]),
            {'count': 3, 'total': 6, 'min': 2, 'max': 2},
        )

    def test_fractional_values(self):
        self.assertEqual(
            statistics_app.summarize_numbers([0.5, 1.25, -0.75]),
            {'count': 3, 'total': 1.0, 'min': -0.75, 'max': 1.25},
        )

    def test_input_not_modified(self):
        values = [3, -1, 3, 0.5]
        original = list(values)
        statistics_app.summarize_numbers(values)
        self.assertEqual(values, original)


if __name__ == '__main__':
    unittest.main()
