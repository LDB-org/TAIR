import argparse
from textutil import slugify

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('text')
    p.add_argument('--slug', action='store_true')
    args=p.parse_args(argv)
    if args.slug:
        print(slugify(args.text))
    else:
        print(args.text)

if __name__=='__main__':
    main()
