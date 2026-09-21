import csv
from collections import defaultdict


def totals(text):
    """Sum integer amounts per category from CSV text.

    The CSV must have a header row with columns 'category' and 'amount'.
    Amounts are integers (may be negative). Returns a dict mapping each
    category to the sum of its amounts. Empty text or header-only input
    returns {}. An invalid amount raises ValueError.
    """
    reader = csv.reader(text.splitlines())
    try:
        header = next(reader)
    except StopIteration:
        return {}

    if [h.strip() for h in header] != ["category", "amount"]:
        raise ValueError("CSV must have header 'category,amount'")

    result = defaultdict(int)
    for row in reader:
        if not row:
            continue
        if len(row) != 2:
            raise ValueError("Each row must have exactly two columns")
        category = row[0]
        amount_str = row[1]
        try:
            amount = int(amount_str)
        except ValueError:
            raise ValueError(f"Invalid amount: {amount_str!r}")
        result[category] += amount

    return dict(result)
