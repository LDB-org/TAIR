import csv
import io


def parse_people(text):
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None:
        return []
    people = []
    for row in reader:
        if not row or not any(cell.strip() for cell in row):
            continue
        name, age, active = row
        people.append({
            'name': name,
            'age': int(age),
            'active': active == 'yes',
        })
    return people
