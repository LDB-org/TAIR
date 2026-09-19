# Text CLI

Run `python app.py "Hello World"` to echo text.

## Slug mode

Pass `--slug` to output a slugified version of the text (lowercased, words
joined with hyphens):

```
$ python app.py --slug "Hello World"
hello-world
```

Whitespace-only input produces an empty string:

```
$ python app.py --slug "   "

```
