import csv


def parse_people(text):
    reader = csv.reader(text.splitlines())
    next(reader, None)  # skip header
    result = []
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        result.append({'name': row[0], 'age': int(row[1]), 'active': row[2] == 'yes'})
    return result
