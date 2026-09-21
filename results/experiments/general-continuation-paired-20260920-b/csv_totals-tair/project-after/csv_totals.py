import csv
import io


def totals(text):
    """Sum integer amounts per category from CSV text.

    The CSV must have a header row with columns category,amount.
    Returns a dict mapping category to the summed integer amount.
    Empty text or header-only input returns {}. An invalid amount
    raises ValueError.
    """
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {}
    if header != ["category", "amount"]:
        raise ValueError("header must be category,amount")
    result = {}
    for row in reader:
        if not row:
            continue
        if len(row) != 2:
            raise ValueError(f"invalid row: {row!r}")
        category, amount_text = row
        try:
            amount = int(amount_text)
        except ValueError:
            raise ValueError(f"invalid amount: {amount_text!r}")
        result[category] = result.get(category, 0) + amount
    return result
