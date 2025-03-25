#!/usr/bin/env python3
"""
HTML to Markdown conversion module.

This module contains functions for converting HTML to Markdown format
and saving Markdown content to files.
"""

import hashlib
import os
import re
from urllib.parse import urlparse

import html2text


def html_to_markdown(html_content, url=""):
    """
    Convert HTML content to markdown format.

    Args:
        html_content: HTML content to convert
        url: URL of the page (for reference)

    Returns:
        str: Markdown formatted content
    """
    # Configure html2text
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_tables = False
    h.ignore_emphasis = False
    h.body_width = 0  # Don't wrap lines

    # Convert to markdown
    markdown_content = h.handle(html_content)

    # Add URL as reference at the top
    if url:
        markdown_content = f"# Page from: {url}\n\n{markdown_content}"

    return markdown_content


def save_markdown_file(domain, category, url, markdown_content):
    """
    Save markdown content to a file in an organized directory structure.

    Args:
        domain: Domain name for the top directory
        category: Category name for the subdirectory
        url: URL of the page (used to create filename)
        markdown_content: Content to save

    Returns:
        str: Path to the saved file
    """
    # Create base directory
    base_dir = f"{domain}_files"
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

    # Create category subdirectory
    category_dir = os.path.join(base_dir, category)
    if not os.path.exists(category_dir):
        os.makedirs(category_dir)

    # Create a filename from the URL
    parsed_url = urlparse(url)
    path = parsed_url.path

    # Handle root path
    if not path or path == "/":
        filename = "index.md"
    else:
        # Clean up path to create filename
        path = path.rstrip("/")
        path = re.sub(r"[^a-zA-Z0-9_-]", "_", path)

        # Add query parameters if present (useful for SPAs)
        if parsed_url.query:
            query_str = re.sub(r"[^a-zA-Z0-9_-]", "_", parsed_url.query)
            path = f"{path}__{query_str}"

        filename = f"{path}.md"

        # Ensure filename is not too long
        if len(filename) > 250:
            filename = (
                filename[:240] + hashlib.md5(filename.encode()).hexdigest()[:10] + ".md"
            )

    # Full path to file
    file_path = os.path.join(category_dir, filename)

    # Write content to file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    return file_path
