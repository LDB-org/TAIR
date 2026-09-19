import argparse

from textutil import slugify


def main():
    p = argparse.ArgumentParser()
    p.add_argument('text')
    p.add_argument('--slug', action='store_true',
                   help='output a slugified version of the text')
    args = p.parse_args()

    if args.slug:
        print(slugify(args.text))
    else:
        print(args.text)


if __name__ == '__main__':
    main()
