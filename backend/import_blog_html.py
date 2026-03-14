#!/usr/bin/env python3
"""
Import static HTML blog articles into the BlogArticle database table.

Reads each frontend/public/blog/*/index.html, extracts French content,
converts HTML to Markdown, and inserts into blog_articles table.

Usage:
    cd backend
    python import_blog_html.py
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BLOG_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "blog"

# Map article-tag text → DB category
TAG_TO_CATEGORY = {
    "guide technique": "dns",
    "dns": "dns",
    "dnssec": "dns",
    "email": "dns",
    "ssl / tls": "ssl",
    "ssl/tls": "ssl",
    "certificats": "ssl",
    "headers http": "headers",
    "en-têtes http": "headers",
    "ports & services": "ports",
    "ports réseau": "ports",
    "réseau": "ports",
    "conformité": "compliance",
    "nis2": "compliance",
    "rgpd": "compliance",
    "comprendre la sécurité": "security",
    "cybersécurité pme": "security",
    "menaces": "security",
    "protection": "security",
    "sécurité applicative": "security",
    "sécurité web": "security",
    "bonnes pratiques": "security",
    "vulnérabilités": "security",
    "cve": "security",
    "gestion de domaine": "dns",
    "e-mail sécurité": "dns",
}


class HTMLToMarkdown:
    """Lightweight HTML→Markdown converter tuned for the blog article structure."""

    def __init__(self):
        self.result = []
        self._in_table = False
        self._table_rows = []
        self._current_row = []
        self._current_cell = []
        self._in_thead = False
        self._in_code_block = False
        self._code_content = []
        self._in_callout = False
        self._callout_type = ""
        self._callout_content = []
        self._in_list = False
        self._list_type = "ul"
        self._list_items = []
        self._current_li = []
        self._skip = False

    def convert(self, html: str) -> str:
        """Convert HTML string to Markdown."""
        # Remove TOC nav
        html = re.sub(r'<nav class="toc"[^>]*>.*?</nav>', '', html, flags=re.DOTALL)
        # Remove CTA block
        html = re.sub(r'<div class="cta-block">.*?</div>\s*</div>', '', html, flags=re.DOTALL)
        # Remove related articles
        html = re.sub(r'<div class="related">.*?</div>\s*</div>\s*</div>', '', html, flags=re.DOTALL)

        self.result = []
        self._process(html)
        text = "\n".join(self.result)
        # Clean up excessive newlines
        text = re.sub(r'\n{4,}', '\n\n\n', text)
        # Remove leading whitespace from non-list/non-code lines
        lines = text.split('\n')
        cleaned = []
        in_code = False
        for line in lines:
            if line.strip().startswith('```'):
                in_code = not in_code
                cleaned.append(line)
            elif in_code:
                cleaned.append(line)
            else:
                cleaned.append(line.strip())
        text = '\n'.join(cleaned)
        # Collapse runs of empty lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _process(self, html: str):
        """Process HTML with regex-based parsing."""
        # Process token by token
        pos = 0
        while pos < len(html):
            # Look for next tag
            tag_match = re.search(r'<(/?)(\w+)([^>]*)>', html[pos:])
            if not tag_match:
                # Remaining text
                text = html[pos:]
                self._handle_text(text)
                break

            # Text before the tag
            text_before = html[pos:pos + tag_match.start()]
            if text_before.strip():
                self._handle_text(text_before)

            tag_name = tag_match.group(2).lower()
            is_closing = tag_match.group(1) == '/'
            attrs_str = tag_match.group(3)
            pos = pos + tag_match.end()

            if is_closing:
                self._handle_close_tag(tag_name)
            else:
                self._handle_open_tag(tag_name, attrs_str)

    def _get_class(self, attrs_str: str) -> str:
        m = re.search(r'class="([^"]*)"', attrs_str)
        return m.group(1) if m else ""

    def _get_id(self, attrs_str: str) -> str:
        m = re.search(r'id="([^"]*)"', attrs_str)
        return m.group(1) if m else ""

    def _handle_open_tag(self, tag: str, attrs: str):
        cls = self._get_class(attrs)

        if tag == 'h2':
            self.result.append("")
            self.result.append(f"## ")
            self._skip = False
            return
        if tag == 'h3':
            self.result.append("")
            self.result.append(f"### ")
            return
        if tag == 'h4':
            self.result.append("")
            self.result.append(f"#### ")
            return
        if tag == 'p':
            if not self._in_callout and not self._in_list:
                self.result.append("")
            return
        if tag == 'strong' or tag == 'b':
            self._append_inline("**")
            return
        if tag == 'em' or tag == 'i':
            self._append_inline("*")
            return
        if tag == 'code' and not self._in_code_block:
            self._append_inline("`")
            return
        if tag == 'a':
            href = re.search(r'href="([^"]*)"', attrs)
            if href:
                self._append_inline(f"[")
            return
        if tag == 'ul':
            self._in_list = True
            self._list_type = "ul"
            self._list_items = []
            self._current_li = []
            self.result.append("")
            return
        if tag == 'ol':
            self._in_list = True
            self._list_type = "ol"
            self._list_items = []
            self._current_li = []
            self.result.append("")
            return
        if tag == 'li':
            self._current_li = []
            return
        if tag == 'table':
            self._in_table = True
            self._table_rows = []
            self._in_thead = False
            return
        if tag == 'thead':
            self._in_thead = True
            return
        if tag == 'tbody':
            self._in_thead = False
            return
        if tag == 'tr':
            self._current_row = []
            return
        if tag in ('th', 'td'):
            self._current_cell = []
            return
        if tag == 'div':
            if 'code-block' in cls:
                self._in_code_block = True
                self._code_content = []
                return
            if 'callout' in cls:
                self._in_callout = True
                if 'callout-warn' in cls:
                    self._callout_type = "warning"
                elif 'callout-ok' in cls:
                    self._callout_type = "tip"
                else:
                    self._callout_type = "info"
                self._callout_content = []
                return
            if 'callout-body' in cls:
                return  # content goes to callout_content
            if 'callout-icon' in cls:
                self._skip = True
                return
        if tag == 'pre':
            if self._in_code_block:
                return
        if tag == 'br':
            self._append_inline("  \n")
            return
        if tag == 'span':
            if 'callout-icon' in cls:
                self._skip = True
            return

    def _handle_close_tag(self, tag: str):
        if tag == 'h2' or tag == 'h3' or tag == 'h4':
            self.result.append("")
            return
        if tag == 'p':
            if self._in_callout:
                return
            return
        if tag == 'strong' or tag == 'b':
            self._append_inline("**")
            return
        if tag == 'em' or tag == 'i':
            self._append_inline("*")
            return
        if tag == 'code' and not self._in_code_block:
            self._append_inline("`")
            return
        if tag == 'a':
            # We need the href — but since we don't track it here,
            # just close the bracket. We'll handle links via regex post-processing.
            self._append_inline("]")
            return
        if tag == 'li':
            li_text = "".join(self._current_li).strip()
            if self._in_list:
                if self._list_type == "ul":
                    self.result.append(f"- {li_text}")
                else:
                    self.result.append(f"{len(self._list_items) + 1}. {li_text}")
                self._list_items.append(li_text)
            return
        if tag in ('ul', 'ol'):
            self._in_list = False
            self.result.append("")
            return
        if tag in ('th', 'td'):
            cell_text = "".join(self._current_cell).strip()
            self._current_row.append(cell_text)
            return
        if tag == 'tr':
            self._table_rows.append(self._current_row)
            return
        if tag == 'thead':
            self._in_thead = False
            return
        if tag == 'table':
            self._in_table = False
            self._render_table()
            return
        if tag == 'div':
            if self._in_code_block:
                code = "\n".join(self._code_content)
                self.result.append("")
                self.result.append("```")
                self.result.append(code)
                self.result.append("```")
                self.result.append("")
                self._in_code_block = False
                return
            if self._in_callout:
                content = "".join(self._callout_content).strip()
                self.result.append("")
                self.result.append(f"> **{self._callout_type.upper()}** : {content}")
                self.result.append("")
                self._in_callout = False
                return
        if tag == 'span':
            self._skip = False
            return

    def _handle_text(self, text: str):
        if self._skip:
            return

        # Decode HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)

        # Normalize whitespace (HTML indentation → single spaces)
        clean = re.sub(r'\s+', ' ', text).strip()
        if not clean:
            return

        if self._in_code_block:
            self._code_content.append(clean)
            return
        if self._in_callout:
            self._callout_content.append(text)
            return
        if self._in_table:
            self._current_cell.append(text)
            return
        if self._in_list:
            self._current_li.append(text)
            return

        self._append_inline(text)

    def _append_inline(self, text: str):
        if self._in_list:
            self._current_li.append(text)
            return
        if self._in_callout:
            self._callout_content.append(text)
            return
        if self._in_table:
            self._current_cell.append(text)
            return
        if self.result:
            self.result[-1] = self.result[-1] + text
        else:
            self.result.append(text)

    def _render_table(self):
        if not self._table_rows:
            return
        self.result.append("")
        header = self._table_rows[0]
        self.result.append("| " + " | ".join(header) + " |")
        self.result.append("| " + " | ".join("---" for _ in header) + " |")
        for row in self._table_rows[1:]:
            # Pad row if needed
            while len(row) < len(header):
                row.append("")
            self.result.append("| " + " | ".join(row) + " |")
        self.result.append("")


def extract_article_data(html_path: Path) -> dict | None:
    """Extract article metadata and content from an HTML file."""
    html = html_path.read_text(encoding="utf-8")

    slug = html_path.parent.name

    # Title from <title> tag (French)
    title_match = re.search(r'<title>(.*?)(?:\s*\|\s*Wezea)?</title>', html)
    title = title_match.group(1).strip() if title_match else slug

    # Also try WZ_T for cleaner title
    wzt_match = re.search(r'window\.WZ_T\s*=\s*(\{.*?\});', html, re.DOTALL)
    if wzt_match:
        try:
            # Parse the JS object (it's almost JSON)
            js_obj = wzt_match.group(1)
            # Extract fr.title
            fr_title = re.search(r'fr:\s*\{[^}]*title:\s*"([^"]*)"', js_obj)
            if fr_title:
                t = fr_title.group(1).replace(' | Wezea', '').strip()
                if t:
                    title = t
        except Exception:
            pass

    # Meta description
    desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    meta_description = desc_match.group(1) if desc_match else None

    # Published date from JSON-LD
    date_match = re.search(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})"', html)
    published_at = None
    if date_match:
        published_at = datetime.strptime(date_match.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Extract French content block — everything between lang-fr and lang-en
    fr_start = html.find('<div class="lang-fr">')
    fr_end = html.find('<div class="lang-en">')
    if fr_start == -1:
        print(f"  WARNING: No lang-fr block found in {slug}")
        return None
    fr_html = html[fr_start:fr_end] if fr_end != -1 else html[fr_start:]

    # Category from article-tag (can be <div> or <span>)
    tag_match = re.search(r'<(?:div|span) class="article-tag">([^<]+)</(?:div|span)>', fr_html)
    raw_tag = tag_match.group(1).strip().lower() if tag_match else ""
    category = TAG_TO_CATEGORY.get(raw_tag, "security")

    # Reading time
    time_match = re.search(r'(\d+)\s*min\s*de\s*lecture', fr_html)
    reading_time = int(time_match.group(1)) if time_match else 5

    # Extract article body — can be <article class="article-body"> or <div class="article-body">
    # Find the start of the article-body block
    body_start = re.search(r'<(?:article|div) class="article-body">', fr_html)
    if not body_start:
        print(f"  WARNING: No article-body found in {slug}")
        return None

    # Content starts after the opening tag
    content_start = body_start.end()
    # Find the end: look for </article> or </div> that closes article-body
    # Use a simple approach: find the closing tag for article-body by looking at the remaining HTML
    remaining = fr_html[content_start:]
    # The article body ends at the last </article> or before a closing </div> that leads to lang-en
    # Safest: take everything until we see the related section or end of lang-fr block
    # Cut at "related" div or CTA block or end
    for end_pattern in [r'<div class="related">', r'<div class="cta-block">', r'</article>', r'</div>\s*</div>\s*<div class="lang-en">']:
        end_match = re.search(end_pattern, remaining)
        if end_match:
            body_html = remaining[:end_match.start()]
            break
    else:
        body_html = remaining

    # Convert HTML to Markdown
    converter = HTMLToMarkdown()
    content_md = converter.convert(body_html)

    # Post-process: fix links (simple href extraction)
    # Find <a href="...">text</a> patterns we missed
    # The converter outputs [text] without href, so let's do a second pass on the original HTML
    links = {}
    for m in re.finditer(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', body_html, re.DOTALL):
        link_text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        link_href = m.group(1)
        if link_text and link_href:
            links[link_text] = link_href

    # Replace [text] with [text](href) where we have a match
    for text, href in links.items():
        content_md = content_md.replace(f"[{text}]", f"[{text}]({href})")

    # Extract intro paragraph
    intro_match = re.search(r'<p class="article-intro">\s*(.*?)\s*</p>', fr_html, re.DOTALL)
    if intro_match:
        intro_text = re.sub(r'<[^>]+>', '', intro_match.group(1)).strip()
        content_md = intro_text + "\n\n" + content_md

    return {
        "slug": slug,
        "title": title,
        "meta_description": meta_description,
        "content_md": content_md,
        "category": category,
        "tags": json.dumps([category, raw_tag]) if raw_tag else json.dumps([category]),
        "author": "Wezea",
        "reading_time_min": reading_time,
        "is_published": True,
        "published_at": published_at,
    }


def main():
    from app.database import SessionLocal, init_db
    from app.models import BlogArticle

    init_db()
    db = SessionLocal()

    article_dirs = sorted([
        d for d in BLOG_DIR.iterdir()
        if d.is_dir() and (d / "index.html").exists()
    ])

    print(f"Found {len(article_dirs)} article directories")

    imported = 0
    skipped = 0

    for article_dir in article_dirs:
        slug = article_dir.name
        html_path = article_dir / "index.html"

        # Check if already exists
        existing = db.query(BlogArticle).filter(BlogArticle.slug == slug).first()
        if existing:
            print(f"  SKIP (already exists): {slug}")
            skipped += 1
            continue

        print(f"  Importing: {slug}")
        data = extract_article_data(html_path)
        if not data:
            print(f"    FAILED: could not extract data")
            continue

        article = BlogArticle(**data)
        db.add(article)
        imported += 1

    db.commit()
    db.close()

    print(f"\nDone! Imported: {imported}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
