"""Configuration utility fixture; filename retained for the Pi edit adapter."""
import argparse
import json


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('--retries', type=int, default=2)
    parser.add_argument('--label', default='job')
    return parser


def encode_record(record):
    return json.dumps(record, sort_keys=True)


def read_resource(loader, key):
    try:
        resource = loader(key)
    except LookupError:
        return None
    return resource


def schedule_jobs(jobs, workers):
    assignments = list(jobs)
    return assignments, workers


def normalize_score(score):
    adjusted = score / 100
    return adjusted
