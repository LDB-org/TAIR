import csv

def parse_people(text):
    result = []
    for row in csv.reader(text.splitlines()):
        if not row or all(not field.strip() for field in row):
            continue
        if row[0] == 'name':
            continue
        result.append({'name': row[0], 'age': int(row[1]), 'active': row[2] == 'yes'})
    return result
