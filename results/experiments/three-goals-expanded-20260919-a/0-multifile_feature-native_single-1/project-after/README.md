# Text CLI

Run `python app.py "Hello World"` to echo text.

## Slug mode

Pass the `--slug` flag to output a URL-friendly slug instead of echoing the
original text. The text is lowercased, split on whitespace, and the words are
joined with hyphens.

```sh
$ python app.py "Hello World"
Hello World

$ python app.py --slug "Hello World"
hello-world
```
