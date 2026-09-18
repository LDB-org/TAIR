import argparse
def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', '-w', type=int, default=4)
    return p
