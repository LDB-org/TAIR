# Text CLI

Run `python app.py "Hello World"` to echo text.

## Slug mode

Pass the `--slug` flag to output a URL-friendly slug instead of echoing the
text. The text is lowercased, split on whitespace, and joined with hyphens.

```
$ python app.py "Hello World"
Hello World

$ python app.py --slug "Hello World"
hello-world
```
