import csv
import io


def parse_people(text):
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None:
        return []
    records = []
    for row in reader:
        if not row or all(not field.strip() for field in row):
            continue
        name, age, active = row
        records.append({
            'name': name,
            'age': int(age),
            'active': active == 'yes',
        })
    return records
