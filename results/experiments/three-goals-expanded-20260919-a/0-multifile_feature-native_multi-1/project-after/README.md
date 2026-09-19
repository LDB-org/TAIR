# Text CLI

Run `python app.py "Hello World"` to echo text.

## Slug mode

Pass the `--slug` flag to output a URL-friendly slug instead of echoing the
original text. The text is lowercased, split on whitespace, and the words are
joined with hyphens.

```bash
$ python app.py "Hello World"
Hello World

$ python app.py "Hello World" --slug
hello-world
```

Whitespace-only input produces an empty string in slug mode.
