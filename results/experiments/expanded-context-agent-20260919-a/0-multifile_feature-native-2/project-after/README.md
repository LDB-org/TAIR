# Text CLI

Run `python app.py "Hello World"` to echo text.

Use the `--slug` flag to output a URL-friendly slug instead:

```
python app.py --slug "Hello World"
# hello-world
```

Whitespace-only input produces an empty slug:

```
python app.py --slug "   "
# (empty)
```
