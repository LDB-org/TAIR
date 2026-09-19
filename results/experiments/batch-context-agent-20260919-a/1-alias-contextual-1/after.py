import argparse
def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('-w', '--workers', type=int, default=4)
    return p
