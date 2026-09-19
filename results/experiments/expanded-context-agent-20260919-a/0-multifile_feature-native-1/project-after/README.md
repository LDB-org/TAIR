# Text CLI

Run `python app.py "Hello World"` to echo text.

## Slug mode

Use the opt-in `--slug` flag to output a slugified version of the text
(lowercased, words joined with hyphens):

```
$ python app.py --slug "Hello World"
hello-world
```

Without `--slug`, the original text is echoed unchanged:

```
$ python app.py "Hello World"
Hello World
```
