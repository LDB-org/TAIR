import csv
import io


def totals(text):
    """Sum integer amounts per category from CSV text."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        return {}
    if not header:
        return {}
    result = {}
    for row in reader:
        if not row:
            continue
        category = row[0]
        amount = int(row[1])
        result[category] = result.get(category, 0) + amount
    return result
