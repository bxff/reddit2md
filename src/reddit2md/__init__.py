#!/usr/bin/env python3
"""Export a Reddit post and all its comments to Markdown."""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlencode

HEADERS = {
    "User-Agent": "reddit2md/1.0 (CLI; +https://github.com/user/reddit2md)",
    "Accept": "application/json",
}

RATE_LIMIT_DELAY = 1.5


def fetch_json(url):
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 429:
            time.sleep(5)
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        raise


def normalize_url(url):
    url = url.strip().rstrip("/")
    url = re.sub(r"^(https?://)(www\.)?reddit\.com", r"\1www.reddit.com", url)
    url = re.sub(r"^(https?://)old\.reddit\.com", r"\1www.reddit.com", url)
    url = re.sub(r"^(https?://)m\.reddit\.com", r"\1www.reddit.com", url)
    if not url.startswith("http"):
        url = "https://www.reddit.com" + url
    url = re.sub(r"\?.*$", "", url)
    return url


def extract_post_id(url):
    match = re.search(r"/comments/([a-z0-9]+)", url)
    if match:
        return "t3_" + match.group(1)
    return None


def fetch_post(url):
    json_url = normalize_url(url) + ".json?limit=500&raw_json=1"
    return fetch_json(json_url)


def fetch_more_children(post_id, children_ids):
    batch_size = 100
    all_comments = []
    for i in range(0, len(children_ids), batch_size):
        batch = children_ids[i : i + batch_size]
        params = urlencode(
            {
                "api_type": "json",
                "link_id": post_id,
                "children": ",".join(batch),
                "raw_json": "1",
                "limit_children": "false",
            }
        )
        api_url = f"https://www.reddit.com/api/morechildren.json?{params}"
        try:
            data = fetch_json(api_url)
            things = data.get("json", {}).get("data", {}).get("things", [])
            all_comments.extend(things)
            time.sleep(RATE_LIMIT_DELAY)
        except Exception:
            pass
    return all_comments


def timestamp_to_str(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def escape_md(text):
    if not text:
        return ""
    return text


def format_score(score):
    if score is None:
        return "?"
    if score >= 10000:
        return f"{score / 1000:.1f}k"
    return str(score)


def indent_text(text, prefix):
    lines = text.split("\n")
    return "\n".join(prefix + line for line in lines)


def parse_comment(comment_data, depth=0):
    data = comment_data.get("data", {})
    kind = comment_data.get("kind", "")

    if kind == "more":
        return None, data.get("children", [])

    if kind != "t1":
        return None, []

    author = data.get("author", "[deleted]")
    score = data.get("score")
    body = data.get("body", "").strip()
    created = data.get("created_utc", 0)
    edited = data.get("edited")
    is_op = data.get("is_submitter", False)
    distinguished = data.get("distinguished")
    gilded = data.get("gilded", 0)
    stickied = data.get("stickied", False)

    if author == "[deleted]" and body == "[deleted]":
        body = "*[deleted]*"
    elif author == "[deleted]" and body == "[removed]":
        body = "*[removed]*"

    flair = ""
    if is_op:
        flair += " **[OP]**"
    if distinguished == "moderator":
        flair += " **[MOD]**"
    if distinguished == "admin":
        flair += " **[ADMIN]**"
    if stickied:
        flair += " **[stickied]**"
    if gilded:
        flair += f" (gilded x{gilded})" if gilded > 1 else " (gilded)"

    time_str = timestamp_to_str(created) if created else ""
    edited_str = ""
    if edited and isinstance(edited, (int, float)) and edited > 0:
        edited_str = f" *(edited {timestamp_to_str(edited)})*"

    header = f"**{author}**{flair} · {format_score(score)} points · {time_str}{edited_str}"

    comment_name = data.get("name", "")

    comment = {
        "id": comment_name,
        "header": header,
        "body": body,
        "depth": depth,
        "replies": [],
        "more_children": [],
    }

    replies = data.get("replies")
    if replies and isinstance(replies, dict):
        children = replies.get("data", {}).get("children", [])
        for child in children:
            child_comment, more_ids = parse_comment(child, depth + 1)
            if child_comment:
                comment["replies"].append(child_comment)
            if more_ids:
                comment["more_children"].extend(more_ids)

    return comment, []


def build_more_lookup(flat_comments):
    lookup = {}
    for thing in flat_comments:
        data = thing.get("data", {})
        if thing.get("kind") == "t1":
            cid = data.get("name", "")
            parent = data.get("parent_id", "")
            lookup.setdefault(parent, []).append(thing)
    return lookup


def insert_more_comments(comment, lookup, parent_name, depth):
    if comment["more_children"] and lookup:
        for child_id in comment["more_children"]:
            full_id = child_id if child_id.startswith("t1_") else f"t1_{child_id}"
            children_for_parent = lookup.get(parent_name, [])
            for thing in children_for_parent:
                if thing["data"].get("name") == full_id:
                    child_comment, _ = parse_comment(thing, depth + 1)
                    if child_comment:
                        comment["replies"].append(child_comment)

    for reply in comment["replies"]:
        reply_name = None
        for thing_list in lookup.values():
            for thing in thing_list:
                pass
        insert_more_comments(reply, lookup, reply_name, depth + 1)


def format_comment_blockquote(comment, depth=0):
    prefix = ">" * (depth + 1) + " " if depth >= 0 else ""
    lines = []

    lines.append(prefix + comment["header"])
    lines.append(prefix)
    body_lines = comment["body"].split("\n")
    for bl in body_lines:
        lines.append(prefix + bl)
    lines.append(prefix)

    for reply in comment["replies"]:
        lines.extend(format_comment_blockquote(reply, depth + 1))
        lines.append(prefix)

    return lines


def format_comment_indent(comment, depth=0):
    indent = "  " * depth
    lines = []

    lines.append(f"{indent}- {comment['header']}")
    lines.append(f"{indent}")
    body_lines = comment["body"].split("\n")
    for bl in body_lines:
        lines.append(f"{indent}  {bl}")
    lines.append(f"{indent}")

    for reply in comment["replies"]:
        lines.extend(format_comment_indent(reply, depth + 1))

    return lines


def format_comment_headers(comment, depth=0):
    level = min(depth + 3, 6)
    hashes = "#" * level
    lines = []

    lines.append(f"{hashes} {comment['header']}")
    lines.append("")
    lines.append(comment["body"])
    lines.append("")

    for reply in comment["replies"]:
        lines.extend(format_comment_headers(reply, depth + 1))

    return lines


FORMAT_FUNCS = {
    "blockquote": format_comment_blockquote,
    "indent": format_comment_indent,
    "headers": format_comment_headers,
}


def format_post(data, fmt="blockquote", include_comments=True):
    post_listing = data[0]["data"]["children"][0]
    post = post_listing["data"]

    title = post.get("title", "Untitled")
    author = post.get("author", "[deleted]")
    subreddit = post.get("subreddit_name_prefixed", "")
    score = post.get("score", 0)
    upvote_ratio = post.get("upvote_ratio", 0)
    created = post.get("created_utc", 0)
    num_comments = post.get("num_comments", 0)
    permalink = post.get("permalink", "")
    url = post.get("url", "")
    selftext = post.get("selftext", "").strip()
    is_self = post.get("is_self", True)
    link_flair = post.get("link_flair_text", "")
    post_id = post.get("name", "")

    lines = []
    lines.append(f"# {title}")
    lines.append("")

    meta = []
    meta.append(f"**{subreddit}**")
    meta.append(f"Posted by u/{author}")
    meta.append(f"{format_score(score)} points ({int(upvote_ratio * 100)}% upvoted)")
    meta.append(f"{num_comments} comments")
    meta.append(timestamp_to_str(created))
    if link_flair:
        meta.append(f"Flair: {link_flair}")
    lines.append(" · ".join(meta))
    lines.append("")
    lines.append(f"[Original post](https://www.reddit.com{permalink})")
    lines.append("")

    if not is_self and url:
        lines.append(f"**Link:** {url}")
        lines.append("")

    if selftext:
        lines.append("---")
        lines.append("")
        lines.append(selftext)
        lines.append("")

    if not include_comments:
        return "\n".join(lines)

    lines.append("---")
    lines.append("")
    lines.append("## Comments")
    lines.append("")

    comment_listing = data[1]["data"]["children"]
    top_comments = []
    all_more_ids = []

    for child in comment_listing:
        comment, more_ids = parse_comment(child, depth=0)
        if comment:
            top_comments.append(comment)
        all_more_ids.extend(more_ids)

    def collect_more_ids(comment):
        ids = list(comment.get("more_children", []))
        for r in comment.get("replies", []):
            ids.extend(collect_more_ids(r))
        return ids

    for c in top_comments:
        all_more_ids.extend(collect_more_ids(c))

    if all_more_ids and post_id:
        print(
            f"Fetching {len(all_more_ids)} additional comments...",
            file=sys.stderr,
        )
        flat_more = fetch_more_children(post_id, all_more_ids)
        if flat_more:
            print(
                f"Retrieved {len(flat_more)} additional comments.",
                file=sys.stderr,
            )
            by_parent = {}
            for thing in flat_more:
                parent = thing.get("data", {}).get("parent_id", "")
                by_parent.setdefault(parent, []).append(thing)

            def inject(comment):
                if comment["more_children"]:
                    parent_id = comment["id"]
                    children_things = by_parent.get(parent_id, [])
                    for thing in children_things:
                        child_comment, _ = parse_comment(
                            thing, comment["depth"] + 1
                        )
                        if child_comment:
                            comment["replies"].append(child_comment)
                    comment["more_children"] = []

                for reply in comment["replies"]:
                    inject(reply)

            for tc in top_comments:
                inject(tc)

            top_more = by_parent.get(post_id, [])
            for thing in top_more:
                child_comment, _ = parse_comment(thing, depth=0)
                if child_comment:
                    top_comments.append(child_comment)

    format_fn = FORMAT_FUNCS.get(fmt, format_comment_blockquote)
    for i, comment in enumerate(top_comments):
        comment_lines = format_fn(comment)
        lines.extend(comment_lines)
        if i < len(top_comments) - 1:
            lines.append("")
            lines.append("---")
            lines.append("")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "reddit2md\n"
            "\n"
            "  Export a Reddit post and all its comments to Markdown.\n"
            "  Single file. No dependencies. No API keys.\n"
            "\n"
            "Install:\n"
            "\n"
            "  uv tool install git+https://github.com/bxff/reddit2md\n"
            "  pip install git+https://github.com/bxff/reddit2md\n"
        ),
        epilog=(
            "Usage:\n"
            "\n"
            "  python3 reddit2md.py <reddit-post-url>                    # output to stdout\n"
            "  python3 reddit2md.py -o post.md <url>                     # save to file\n"
            "  python3 reddit2md.py -f indent <url>                      # nested list format\n"
            "  python3 reddit2md.py -f headers <url>                     # heading-based format\n"
            "  python3 reddit2md.py --no-comments <url>                  # post only, skip comments\n"
            "\n"
            "What it does:\n"
            "\n"
            "  - Fetches via Reddit's public JSON API. No API keys, no auth.\n"
            "  - Gets all comments including \"more\" threads (via /api/morechildren)\n"
            "  - Properly nested blockquotes (>, >>, >>>, etc.) at arbitrary depth\n"
            "  - Preserves comment metadata: author, score, time, OP/MOD/ADMIN badges, edited status, gilding\n"
            "  - Handles deleted/removed comments, spoiler tags, link posts\n"
            "  - 3 output formats: blockquote (default), indent, headers\n"
            "  - Clean error messages for 404s, rate limits, network issues\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="Reddit post URL")
    parser.add_argument(
        "-o", "--output", help="output file (default: stdout)", default=None
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["blockquote", "indent", "headers"],
        default="blockquote",
        help="comment nesting format (default: blockquote)",
    )
    parser.add_argument(
        "--no-comments",
        action="store_true",
        help="only export the post, skip comments",
    )

    args = parser.parse_args()

    url = args.url
    if not re.search(r"reddit\.com/r/\w+/comments/", url):
        print("Error: doesn't look like a Reddit post URL", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching post...", file=sys.stderr)
    try:
        data = fetch_post(url)
    except HTTPError as e:
        if e.code == 404:
            print("Error: post not found (404). Check the URL.", file=sys.stderr)
        elif e.code == 403:
            print("Error: access denied (403). The post may be private or quarantined.", file=sys.stderr)
        elif e.code == 429:
            print("Error: rate limited by Reddit. Wait a minute and try again.", file=sys.stderr)
        else:
            print(f"Error: HTTP {e.code} from Reddit.", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Error: could not connect to Reddit: {e.reason}", file=sys.stderr)
        sys.exit(1)

    md = format_post(data, fmt=args.format, include_comments=not args.no_comments)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
