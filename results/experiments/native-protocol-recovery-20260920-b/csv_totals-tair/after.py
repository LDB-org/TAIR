import csv
import io


def totals(text):
    """Sum integer amounts per category from CSV text with header category,amount.

    Supports quoted commas in category names, negative numbers and Unicode.
    Empty text or header-only input returns {}. An invalid amount raises
    ValueError.
    """
    reader = csv.DictReader(io.StringIO(text))
    result = {}
    for row in reader:
        category = row["category"]
        amount = int(row["amount"])
        result[category] = result.get(category, 0) + amount
    return result
