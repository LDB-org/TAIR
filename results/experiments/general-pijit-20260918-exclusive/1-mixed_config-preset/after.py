import argparse

def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=6)
    p.add_argument('--timeout', type=float, default=2.5)
    p.add_argument('--host', default='localhost')
    return p
