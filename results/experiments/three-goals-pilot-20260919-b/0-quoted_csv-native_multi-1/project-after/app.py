import csv
import io


def parse_people(text):
    reader = csv.reader(io.StringIO(text))
    next(reader, None)  # skip header
    result = []
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue  # ignore blank records
        result.append({
            'name': row[0],
            'age': int(row[1]),
            'active': row[2] == 'yes',
        })
    return result
