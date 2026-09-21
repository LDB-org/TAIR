import csv
from collections import defaultdict
from io import StringIO


def totals(text):
    """Parse CSV with header category,amount and sum integer amounts per category.

    Returns a dict mapping category -> total. Empty text or header-only input
    returns {}. An invalid amount raises ValueError.
    """
    if not text or not text.strip():
        return {}

    reader = csv.reader(StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {}

    if not header or header[0].strip().lower() != "category" or header[1].strip().lower() != "amount":
        raise ValueError("CSV must have header 'category,amount'")

    result = defaultdict(int)
    for row in reader:
        if not row:
            continue
        if len(row) < 2:
            raise ValueError(f"Invalid row: {row}")
        category = row[0]
        amount_str = row[1]
        try:
            amount = int(amount_str)
        except ValueError:
            raise ValueError(f"Invalid amount: {amount_str!r}") from None
        result[category] += amount

    return dict(result)
