import argparse

def main():
    p=argparse.ArgumentParser()
    p.add_argument('text')
    args=p.parse_args()
    print(args.text)

if __name__=='__main__':
    main()
