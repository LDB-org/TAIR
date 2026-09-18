"""Configuration utility fixture; filename retained for the Pi edit adapter."""
import argparse
import json


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--retries', type=int, default=2)
    parser.add_argument('--label', default='job')
    return parser


def encode_record(record):
    if any((isinstance(v, float) and (v != v or v in (float('inf'), float('-inf'))) for v in record.values())):
        raise ValueError('NaN and Infinity are not valid JSON values')
    return json.dumps(record, sort_keys=True)


def read_resource(loader, key):
    resource = loader(key)
    return resource


def schedule_jobs(jobs, workers):
    assignments = list(jobs)
    return assignments, workers


def normalize_score(score):
    adjusted = score / 100
    return adjusted
