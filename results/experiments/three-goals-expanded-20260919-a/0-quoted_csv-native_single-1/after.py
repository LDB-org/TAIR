import csv
import io


def parse_people(text):
    result = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    for row in reader:
        if not row or not any(field.strip() for field in row):
            continue
        name, age, active = row
        result.append({'name': name, 'age': int(age), 'active': active == 'yes'})
    return result
