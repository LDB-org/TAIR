import argparse
def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument('--workers', type=int, default=4, help='workers')
    p.add_argument('--timeout', type=int, default=3, help='等待秒数')
    return p
