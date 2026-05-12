reddit2md

  Export a Reddit post and all its comments to Markdown.
  Single file. No dependencies. No API keys.

Install:

  uv tool install git+https://github.com/bxff/reddit2md
  pip install git+https://github.com/bxff/reddit2md

Usage:

  python3 reddit2md.py <reddit-post-url>                    # output to stdout
  python3 reddit2md.py -o post.md <url>                     # save to file
  python3 reddit2md.py -f indent <url>                      # nested list format
  python3 reddit2md.py -f headers <url>                     # heading-based format
  python3 reddit2md.py --no-comments <url>                  # post only, skip comments

What it does:

  - Fetches via Reddit's public JSON API. No API keys, no auth.
  - Gets all comments including "more" threads (via /api/morechildren)
  - Properly nested blockquotes (>, >>, >>>, etc.) at arbitrary depth
  - Preserves comment metadata: author, score, time, OP/MOD/ADMIN badges, edited status, gilding
  - Handles deleted/removed comments, spoiler tags, link posts
  - 3 output formats: blockquote (default), indent, headers
  - Clean error messages for 404s, rate limits, network issues
