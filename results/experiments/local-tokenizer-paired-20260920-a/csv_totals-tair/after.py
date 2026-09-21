import csv
import io


def totals(text):
    """Sum integer amounts per category from CSV text with header category,amount."""
    result = {}
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {}
    if header != ["category", "amount"]:
        raise ValueError("invalid header")
    for row in reader:
        if not row:
            continue
        if len(row) != 2:
            raise ValueError("invalid row")
        category, amount_str = row
        try:
            amount = int(amount_str)
        except ValueError:
            raise ValueError(f"invalid amount: {amount_str!r}")
        result[category] = result.get(category, 0) + amount
    return result
