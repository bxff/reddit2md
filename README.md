# reddit2md

Export a Reddit post and all its comments to Markdown. Single file, no dependencies, no API keys.

## Usage

```
python3 reddit2md.py <reddit-post-url>
python3 reddit2md.py -o post.md <url>
python3 reddit2md.py -f indent <url>
python3 reddit2md.py -f headers <url>
python3 reddit2md.py --no-comments <url>
```

## Options

| Flag | Description |
|------|-------------|
| `-o, --output` | Output file (default: stdout) |
| `-f, --format` | `blockquote` (default), `indent`, or `headers` |
| `--no-comments` | Only export the post, skip comments |
