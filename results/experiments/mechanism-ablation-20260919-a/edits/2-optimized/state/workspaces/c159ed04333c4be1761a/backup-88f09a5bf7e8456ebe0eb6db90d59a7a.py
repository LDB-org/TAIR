import argparse
def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=4)
    return p
# unrelated comment
