import argparse

from textutil import slugify

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('text', nargs='*')
    p.add_argument('--slug', action='store_true', help='Output a URL-friendly slug')
    args=p.parse_args(argv)
    text=' '.join(args.text)
    if args.slug:
        print(slugify(text))
    else:
        print(text)

if __name__=='__main__':
    main()
