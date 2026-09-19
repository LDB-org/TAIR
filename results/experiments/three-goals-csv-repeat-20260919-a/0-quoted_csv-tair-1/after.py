import csv


def parse_people(text):
    rows = csv.reader(text.splitlines())
    next(rows, None)  # skip header
    result = []
    for row in rows:
        if not row or not any(cell.strip() for cell in row):
            continue
        result.append({'name': row[0], 'age': int(row[1]), 'active': row[2] == 'yes'})
    return result
