import argparse

def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=4, help='old', required=False)
    p.add_argument('--timeout', type=float, default=1.5)
    p.add_argument('--host', default='localhost')
    p.add_argument('--verbose', action='store_true', default=False)
    return p
