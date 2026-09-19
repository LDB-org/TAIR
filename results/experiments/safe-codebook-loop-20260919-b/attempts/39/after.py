import argparse
def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=10, help='workers')
    p.add_argument('--timeout', type=int, default=3, help='timeout')
    return p
