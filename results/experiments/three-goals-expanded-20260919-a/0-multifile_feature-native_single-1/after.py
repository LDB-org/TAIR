import argparse

from textutil import slugify

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('text')
    p.add_argument('--slug', action='store_true',
                   help='output a URL-friendly slug instead of echoing the text')
    args = p.parse_args(argv)

    if args.slug:
        return slugify(args.text)
    return args.text

if __name__ == '__main__':
    print(main())
