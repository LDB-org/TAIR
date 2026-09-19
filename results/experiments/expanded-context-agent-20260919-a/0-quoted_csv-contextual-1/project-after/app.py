import csv

def parse_people(text):
    return [{'name': row['name'], 'age': int(row['age']), 'active': row['active']=='yes'}
            for row in csv.DictReader(text.splitlines())
            if any(row.values())]
