#!/usr/bin/env python3
"""
t0m-sec Blog — LLM Translation Script

Translates Japanese Markdown blog posts to English using Google Gemini API.
Implements caching (MD5 hash) to avoid re-translating unchanged posts.
"""

import hashlib
import json
import os
import sys
from pathlib import Path
import traceback

import frontmatter
import yaml

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "posts"
TRANSLATIONS_DIR = CONTENT_DIR / ".translations"
CACHE_FILE = TRANSLATIONS_DIR / "_cache.json"
CONFIG_FILE = ROOT / "config.yml"


def load_config():
    """Load site configuration."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_cache():
    """Load translation cache (maps filename -> MD5 hash)."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    """Save translation cache."""
    TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def compute_md5(filepath):
    """Compute MD5 hash of file contents."""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def translate_markdown(content, metadata, model_name="claude-3-7-sonnet-latest"):
    """
    Translate Japanese Markdown content and metadata to English
    using Anthropic Claude API.
    """
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not installed.")
        print("  Run: pip install anthropic")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        print("  Set it in your GitHub repository secrets.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Build translation prompt
    prompt = f"""You are a professional translator specializing in cybersecurity and information technology content.

Translate the following Japanese blog post to natural, professional English.

## Rules:
1. Translate the title, summary, and body content to English
2. Keep ALL code blocks, code snippets, and inline code UNCHANGED
3. Keep ALL image paths and URLs UNCHANGED
4. Keep ALL Markdown formatting intact
5. Keep technical terms in their commonly used English form
6. Translate tags to their English equivalents
7. The category name should remain the same (it's already in English)
8. Maintain the same heading structure and hierarchy
9. Keep the author name unchanged
10. Output ONLY the translated content, no explanations

## Metadata to translate:
- Title: {metadata.get('title', '')}
- Summary: {metadata.get('summary', '')}
- Tags: {metadata.get('tags', [])}

## Body content to translate:

{content}

## Output format:
Return the result in this exact format:

TRANSLATED_TITLE: [translated title here]
TRANSLATED_SUMMARY: [translated summary here]
TRANSLATED_TAGS: [comma-separated translated tags]
---BODY---
[translated markdown body here]
"""

    response = client.messages.create(
        model=model_name,
        max_tokens=8192,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return parse_translation_response(response.content[0].text, metadata)


def parse_translation_response(response_text, original_metadata):
    """Parse the LLM response into metadata and content."""
    lines = response_text.strip().split("\n")

    translated_title = original_metadata.get("title", "")
    translated_summary = original_metadata.get("summary", "")
    translated_tags = original_metadata.get("tags", [])
    body_start = 0

    for i, line in enumerate(lines):
        if line.startswith("TRANSLATED_TITLE:"):
            translated_title = line[len("TRANSLATED_TITLE:"):].strip()
        elif line.startswith("TRANSLATED_SUMMARY:"):
            translated_summary = line[len("TRANSLATED_SUMMARY:"):].strip()
        elif line.startswith("TRANSLATED_TAGS:"):
            tags_str = line[len("TRANSLATED_TAGS:"):].strip()
            translated_tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        elif line.strip() == "---BODY---":
            body_start = i + 1
            break

    translated_body = "\n".join(lines[body_start:]).strip()

    # If parsing failed, use the entire response as body
    if not translated_body:
        translated_body = response_text
        print("  ⚠ Could not parse structured response, using raw output")

    # Build new metadata
    new_metadata = dict(original_metadata)
    new_metadata["title"] = translated_title
    new_metadata["summary"] = translated_summary
    new_metadata["tags"] = translated_tags

    return new_metadata, translated_body


def translate_about_page(model_name="claude-3-7-sonnet-latest"):
    """Translate about_ja.md page to English."""
    about_file = ROOT / "pages" / "about_ja.md"
    about_en_file = ROOT / "pages" / "about_en.md"

    if not about_file.exists():
        print("  ⏭ No about_ja.md found, skipping")
        return

    # Check cache
    cache = load_cache()
    current_hash = compute_md5(about_file)
    cache_key = "about_ja.md"

    if cache.get(cache_key) == current_hash and about_en_file.exists():
        print("  ⏭ about_ja.md unchanged, skipping")
        return

    print("  🔄 Translating about_ja.md...")
    post = frontmatter.load(str(about_file))

    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""Translate the following Japanese 'About' page content to natural, professional English.
Keep ALL Markdown formatting, code blocks, and URLs intact.
Output ONLY the translated Markdown content, no explanations.

{post.content}
"""
        response = client.messages.create(
            model=model_name,
            max_tokens=8192,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Write translated about page
        about_en_file.write_text(
            f"---\ntitle: About\n---\n\n{response.content[0].text.strip()}\n",
            encoding="utf-8",
        )
        cache[cache_key] = current_hash
        save_cache(cache)
        print("  ✓ about_en.md generated")

    except Exception as e:
        print(f"  ✗ Failed to translate about_ja.md: {e}")
        print(traceback.format_exc())


def main():
    """Main translation process."""
    print("=" * 50)
    print("🌐 Translating blog posts (JA → EN)")
    print("=" * 50)

    config = load_config()
    translation_config = config.get("translation", {})

    if not translation_config.get("enabled", False):
        print("Translation is disabled in config.yml")
        return

    model_name = translation_config.get("model", "claude-3-7-sonnet-latest")
    print(f"  Model: {model_name}")

    # Ensure translations directory exists
    TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Load cache
    cache = load_cache()

    # Find all Japanese posts
    md_files = sorted(CONTENT_DIR.glob("*.md"))
    print(f"\n📝 Found {len(md_files)} post(s) to check\n")

    translated_count = 0
    skipped_count = 0

    for md_file in md_files:
        filename = md_file.name
        current_hash = compute_md5(md_file)
        en_file = TRANSLATIONS_DIR / f"{md_file.stem}_en.md"

        # Check if translation is cached and up-to-date
        if cache.get(filename) == current_hash and en_file.exists():
            print(f"  ⏭ {filename} — unchanged, skipping")
            skipped_count += 1
            continue

        print(f"  🔄 {filename} — translating...")

        try:
            # Load post
            post = frontmatter.load(str(md_file))

            # Translate
            new_metadata, translated_body = translate_markdown(
                post.content, post.metadata, model_name
            )

            # Create translated post
            new_post = frontmatter.Post(translated_body, **new_metadata)
            en_file.write_text(
                frontmatter.dumps(new_post), encoding="utf-8"
            )

            # Update cache
            cache[filename] = current_hash
            save_cache(cache)

            translated_count += 1
            print(f"  ✓ {filename} → {en_file.name}")

        except Exception as e:
            print(f"  ✗ Failed to translate {filename}: {e}")
            print(traceback.format_exc())
            print(traceback.format_exc())

    # Translate about page
    print("\n📄 Checking about page...")
    translate_about_page(model_name)

    print(f"\n{'=' * 50}")
    print(f"✅ Translation complete!")
    print(f"   Translated: {translated_count}")
    print(f"   Skipped (cached): {skipped_count}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
