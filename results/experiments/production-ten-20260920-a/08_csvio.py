import csv
from pathlib import Path


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def read_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        return [row for row in reader]
