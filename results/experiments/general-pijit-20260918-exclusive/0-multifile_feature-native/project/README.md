# Text CLI

Run `python app.py "Hello World"` to echo text.

Use the `--slug` flag to output a slugified version of the text:

```
$ python app.py "Hello World"
Hello World

$ python app.py --slug "Hello World"
hello-world
```

The slug is produced by lowercasing the text, splitting on whitespace, and
joining the words with hyphens. Whitespace-only input produces an empty string.
