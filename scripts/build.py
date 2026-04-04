#!/usr/bin/env python3
"""
t0m-sec Blog — Static Site Builder

Converts Markdown posts to HTML using Pandoc and Jinja2 templates.
Generates index, archive, about pages, and RSS feed.
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

import frontmatter
import yaml
from jinja2 import Environment, FileSystemLoader

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "posts"
TRANSLATIONS_DIR = CONTENT_DIR / ".translations"
PAGES_DIR = ROOT / "pages"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
OUTPUT_DIR = ROOT / "public"
CONFIG_FILE = ROOT / "config.yml"


def load_config():
    """Load site configuration from config.yml."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_jinja_env():
    """Create Jinja2 environment with template directory."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
    )
    return env


def get_posts(lang="ja"):
    """
    Scan content/posts/ for Markdown files.
    For 'en' lang, look in .translations/ directory.
    Returns list of post dicts sorted by date descending.
    """
    posts = []
    md_dir = TRANSLATIONS_DIR if lang == "en" else CONTENT_DIR

    for md_file in sorted(CONTENT_DIR.glob("*.md"), reverse=True):
        if lang == "en":
            # Look for translated version
            en_file = TRANSLATIONS_DIR / f"{md_file.stem}_en.md"
            if not en_file.exists():
                # Fallback to Japanese if no translation exists
                target_file = md_file
            else:
                target_file = en_file
        else:
            target_file = md_file

        post = frontmatter.load(str(target_file))
        meta = post.metadata

        # Compute slug from filename: 2026-04-04-sample-post.md -> sample-post
        slug_match = re.match(r"\d{4}-\d{2}-\d{2}-(.*)", md_file.stem)
        slug = slug_match.group(1) if slug_match else md_file.stem

        # Compute reading time and word count
        content = post.content
        word_count = len(content)
        reading_time = max(1, word_count // 500)  # ~500 chars/min for Japanese

        posts.append({
            "slug": slug,
            "title": meta.get("title", slug),
            "date": str(meta.get("date", "")),
            "category": meta.get("category", ""),
            "tags": meta.get("tags", []),
            "summary": meta.get("summary", content[:150] + "..."),
            "author": meta.get("author", ""),
            "content_raw": content,
            "word_count": word_count,
            "reading_time": reading_time,
            "source_file": str(target_file),
            "original_file": str(md_file),
        })

    # Sort by date descending
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def convert_md_to_html(markdown_content):
    """Convert markdown content to HTML using Pandoc."""
    try:
        result = subprocess.run(
            [
                "pandoc",
                "--from=markdown",
                "--to=html5",
                "--no-highlight",
            ],
            input=markdown_content.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        return result.stdout.decode("utf-8")
    except FileNotFoundError:
        print("ERROR: pandoc not found. Please install pandoc.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: pandoc failed: {e.stderr.decode('utf-8', errors='replace')}")
        sys.exit(1)


def convert_md_to_html_highlighted(markdown_content):
    """Convert markdown content to HTML using Pandoc with syntax highlighting."""
    try:
        result = subprocess.run(
            [
                "pandoc",
                "--from=markdown",
                "--to=html5",
                "--highlight-style=breezeDark",
            ],
            input=markdown_content.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        return result.stdout.decode("utf-8")
    except FileNotFoundError:
        print("ERROR: pandoc not found. Please install pandoc.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: pandoc failed: {e.stderr.decode('utf-8', errors='replace')}")
        sys.exit(1)


def get_categories(posts):
    """Extract category counts from posts."""
    cats = {}
    for post in posts:
        cat = post["category"]
        if cat:
            cats[cat] = cats.get(cat, 0) + 1
    return [{"name": k, "count": v} for k, v in sorted(cats.items())]


def get_all_tags(posts):
    """Extract unique tags from all posts."""
    tags = set()
    for post in posts:
        tags.update(post["tags"])
    return sorted(tags)


def build_index(env, config, posts, lang="ja"):
    """Generate index.html (top page)."""
    template = env.get_template("index.html")
    categories = get_categories(posts)
    all_tags = get_all_tags(posts)

    html = template.render(
        site=config["site"] | {"author": config["author"]},
        posts=posts,
        categories=categories,
        all_tags=all_tags,
        lang=lang,
        current_path="/",
        year=datetime.now().year,
        canonical_url=config["site"]["base_url"] + f"/{lang}/",
    )

    out_dir = OUTPUT_DIR / lang

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ index.html ({lang})")


def build_post(env, config, post, lang="ja"):
    """Generate individual post HTML page."""
    template = env.get_template("post.html")

    # Convert markdown to HTML
    content_html = convert_md_to_html_highlighted(post["content_raw"])

    # Build path for this post
    current_path = f"/posts/{post['slug']}/"
    post_dir = OUTPUT_DIR / lang / "posts" / post["slug"]

    html = template.render(
        site=config["site"] | {"author": config["author"]},
        title=post["title"],
        date=post["date"],
        category=post["category"],
        tags=post["tags"],
        summary=post["summary"],
        content=content_html,
        reading_time=post["reading_time"],
        word_count=post["word_count"],
        lang=lang,
        alt_lang="en" if lang == "ja" else "ja",
        current_path=current_path,
        canonical_url=config["site"]["base_url"] + f"/{lang}{current_path}",
        year=datetime.now().year,
    )

    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ posts/{post['slug']}/ ({lang})")


def build_archive(env, config, posts, lang="ja"):
    """Generate posts listing page grouped by year."""
    template = env.get_template("archive.html")

    # Group posts by year
    posts_by_year = OrderedDict()
    for post in posts:
        year = post["date"][:4] if post["date"] else "Unknown"
        if year not in posts_by_year:
            posts_by_year[year] = []
        posts_by_year[year].append(post)

    html = template.render(
        site=config["site"] | {"author": config["author"]},
        posts_by_year=posts_by_year,
        lang=lang,
        current_path="/posts/",
        year=datetime.now().year,
    )

    out_dir = OUTPUT_DIR / lang / "posts"

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ posts/ ({lang})")


def build_about(env, config, lang="ja"):
    """Generate about page."""
    template = env.get_template("about.html")

    # Look for about page content
    about_file = PAGES_DIR / f"about_{lang}.md"

    if about_file.exists():
        post = frontmatter.load(str(about_file))
        content_html = convert_md_to_html_highlighted(post.content)
    else:
        content_html = "<p>Coming soon...</p>"

    html = template.render(
        site=config["site"] | {"author": config["author"]},
        content=content_html,
        lang=lang,
        current_path="/about/",
        year=datetime.now().year,
    )

    out_dir = OUTPUT_DIR / lang / "about"

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"  ✓ about/ ({lang})")



def copy_static():
    """Copy static files to output directory."""
    # CSS
    css_out = OUTPUT_DIR / "css"
    css_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STATIC_DIR / "css" / "style.css", css_out / "style.css")

    # Images
    images_out = OUTPUT_DIR / "images"
    images_src = STATIC_DIR / "images"
    if images_src.exists():
        if images_out.exists():
            shutil.rmtree(images_out)
        shutil.copytree(images_src, images_out)

    # Post images
    post_images_src = CONTENT_DIR / "images"
    if post_images_src.exists():
        post_images_out = OUTPUT_DIR / "posts" / "images"
        if post_images_out.exists():
            shutil.rmtree(post_images_out)
        shutil.copytree(post_images_src, post_images_out)

    # Favicon
    favicon = STATIC_DIR / "favicon.ico"
    if favicon.exists():
        shutil.copy2(favicon, OUTPUT_DIR / "favicon.ico")

    # .nojekyll for GitHub Pages
    (OUTPUT_DIR / ".nojekyll").touch()

    print("  ✓ static files copied")


import argparse


def main():
    """Main build process."""
    parser = argparse.ArgumentParser(description="Build t0m-sec's Blog")
    parser.add_argument(
        "--local", action="store_true",
        help="Build for local preview (sets base_url to empty)"
    )
    parser.add_argument(
        "--base-url", type=str, default=None,
        help="Override base_url (e.g., http://localhost:8080)"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Override output directory (default: public)"
    )
    args = parser.parse_args()

    global OUTPUT_DIR
    if args.output:
        OUTPUT_DIR = Path(args.output).resolve()
        print(f"  📁 Output dir: {OUTPUT_DIR}")

    print("=" * 50)
    print(f"🔧 Building t0m-sec's Blog")
    print("=" * 50)

    # Load config
    config = load_config()

    # Override base_url for local development
    if args.local:
        config["site"]["base_url"] = ""
        print("  ⚡ Local mode: base_url set to ''")
    elif args.base_url:
        config["site"]["base_url"] = args.base_url.rstrip("/")
        print(f"  ⚡ Custom base_url: {config['site']['base_url']}")
    elif not os.environ.get("GITHUB_ACTIONS"):
        # Auto-detect local development: clear base_url for local preview
        config["site"]["base_url"] = ""
        print("  ⚡ Auto-detected local mode: base_url set to ''")

    print(f"\n📄 Config loaded: {config['site']['title']}")

    # Clean output
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # Setup Jinja2
    env = get_jinja_env()

    # Get posts for both languages
    print("\n📝 Processing Japanese posts...")
    posts_ja = get_posts(lang="ja")
    print(f"   Found {len(posts_ja)} post(s)")

    print("\n📝 Processing English posts...")
    posts_en = get_posts(lang="en")
    print(f"   Found {len(posts_en)} post(s)")

    # Build Japanese pages
    print("\n🇯🇵 Building Japanese pages...")
    build_index(env, config, posts_ja, lang="ja")
    for post in posts_ja:
        build_post(env, config, post, lang="ja")
    build_archive(env, config, posts_ja, lang="ja")
    build_about(env, config, lang="ja")

    # Build English pages
    print("\n🇬🇧 Building English pages...")
    build_index(env, config, posts_en, lang="en")
    for post in posts_en:
        build_post(env, config, post, lang="en")
    build_archive(env, config, posts_en, lang="en")
    build_about(env, config, lang="en")



    # Build Root Redirect
    redirect_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="refresh" content="0; url={config["site"]["base_url"]}/ja/">
    <title>Redirecting...</title>
</head>
<body>
    <p>If you are not redirected automatically, follow this <a href="{config["site"]["base_url"]}/ja/">link</a>.</p>
</body>
</html>'''
    (OUTPUT_DIR / "index.html").write_text(redirect_html, encoding="utf-8")
    print("\n🚀 Generated root redirect")

    # Copy static files
    print("\n📦 Copying static files...")
    copy_static()

    print("\n" + "=" * 50)
    print(f"✅ Build complete! Output: {OUTPUT_DIR}")
    print(f"   Total pages: {2 * (len(posts_ja) + 3) + 1}")
    print("=" * 50)


if __name__ == "__main__":
    main()

