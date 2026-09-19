import csv
from io import StringIO

def parse_people(text):
    reader = csv.reader(StringIO(text))
    header = next(reader, None)
    if header is None:
        return []
    result = []
    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue
        result.append({'name': row[0], 'age': int(row[1]), 'active': row[2] == 'yes'})
    return result
