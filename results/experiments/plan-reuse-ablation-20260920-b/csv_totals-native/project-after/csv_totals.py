"""Parse CSV with header category,amount and sum integer amounts per category."""

import csv
import io


def totals(text):
    """Parse CSV text with header 'category,amount'.

    Sums integer amounts per category and returns a dict mapping category
    name to total. Supports quoted commas in category names, negative
    numbers, and Unicode. Empty text or header-only input returns {}.
    Raises ValueError if an amount is not a valid integer.
    """
    if not text:
        return {}

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {}

    # Validate header.
    if [h.strip() for h in header] != ["category", "amount"]:
        raise ValueError("CSV must have header 'category,amount'")

    result = {}
    for row in reader:
        if not row:
            continue
        if len(row) != 2:
            raise ValueError("Each row must have exactly two fields")
        category, amount = row
        try:
            value = int(amount)
        except ValueError:
            raise ValueError(f"Invalid amount: {amount!r}")
        result[category] = result.get(category, 0) + value

    return result
