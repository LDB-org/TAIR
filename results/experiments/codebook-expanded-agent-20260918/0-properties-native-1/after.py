import argparse

def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=4, help='Worker count', required=True)
    p.add_argument('--timeout', type=float, default=2.5)
    p.add_argument('--host', default='remote')
    p.add_argument('--verbose', action='store_false', default=True)
    return p
