import argparse

def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=11)
    p.add_argument('--timeout', type=float, default=3.125, help='Timeout')
    p.add_argument('--host', default='localhost')
    p.add_argument('--verbose', action='store_true', default=False)
    p.add_argument('--token', default='', required=False)
    return p

def checksum(values):
    return sum(values) % 65536
SOURCE_VERSION = 2
