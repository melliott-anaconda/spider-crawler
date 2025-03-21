#!/usr/bin/env python3
"""
HTML to Markdown conversion module.

This module contains functions for converting HTML to Markdown format
and saving Markdown content to files.
"""

import os
import re
import hashlib
from urllib.parse import urlparse

import html2text


def html_to_markdown(html_content, url=''):
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
    if not path or path == '/':
        filename = 'index.md'
    else:
        # Clean up path to create filename
        path = path.rstrip('/')
        path = re.sub(r'[^a-zA-Z0-9_-]', '_', path)
        
        # Add query parameters if present (useful for SPAs)
        if parsed_url.query:
            query_str = re.sub(r'[^a-zA-Z0-9_-]', '_', parsed_url.query)
            path = f"{path}__{query_str}"
        
        filename = f"{path}.md"
        
        # Ensure filename is not too long
        if len(filename) > 250:
            filename = filename[:240] + hashlib.md5(filename.encode()).hexdigest()[:10] + '.md'
    
    # Full path to file
    file_path = os.path.join(category_dir, filename)
    
    # Write content to file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    return file_path


def extract_markdown_metadata(markdown_content):
    """
    Extract metadata from markdown content.
    
    Args:
        markdown_content: Markdown content to analyze
        
    Returns:
        dict: Extracted metadata
    """
    metadata = {}
    
    # Extract title (first heading)
    title_match = re.search(r'^# (.+)$', markdown_content, re.MULTILINE)
    if title_match:
        metadata['title'] = title_match.group(1).strip()
    
    # Extract URL reference
    url_match = re.search(r'^# Page from: (.+)$', markdown_content, re.MULTILINE)
    if url_match:
        metadata['url'] = url_match.group(1).strip()
    
    # Count headings by level
    headings = {
        'h1': len(re.findall(r'^# ', markdown_content, re.MULTILINE)),
        'h2': len(re.findall(r'^## ', markdown_content, re.MULTILINE)),
        'h3': len(re.findall(r'^### ', markdown_content, re.MULTILINE)),
        'h4': len(re.findall(r'^#### ', markdown_content, re.MULTILINE)),
        'h5': len(re.findall(r'^##### ', markdown_content, re.MULTILINE)),
        'h6': len(re.findall(r'^###### ', markdown_content, re.MULTILINE))
    }
    metadata['headings'] = headings
    
    # Count links
    links = re.findall(r'\[.+?\]\(.+?\)', markdown_content)
    metadata['links'] = len(links)
    
    # Count images
    images = re.findall(r'!\[.+?\]\(.+?\)', markdown_content)
    metadata['images'] = len(images)
    
    # Count code blocks
    code_blocks = re.findall(r'```.*?```', markdown_content, re.DOTALL)
    metadata['code_blocks'] = len(code_blocks)
    
    # Estimate word count (excluding code blocks)
    # First, remove code blocks
    text_only = markdown_content
    for block in code_blocks:
        text_only = text_only.replace(block, '')
    
    # Remove markdown syntax and count words
    cleaned_text = re.sub(r'[#*_`\[\]\(\)]', '', text_only)
    words = re.findall(r'\b\w+\b', cleaned_text)
    metadata['word_count'] = len(words)
    
    return metadata


def create_table_of_contents(markdown_content):
    """
    Create a table of contents for markdown content.
    
    Args:
        markdown_content: Markdown content to analyze
        
    Returns:
        str: Table of contents in markdown format
    """
    toc_lines = ["# Table of Contents\n"]
    
    # Find all headings
    heading_pattern = re.compile(r'^(#+) (.+)$', re.MULTILINE)
    headings = heading_pattern.findall(markdown_content)
    
    for level, title in headings:
        # Skip the TOC heading itself
        if title.lower() == "table of contents":
            continue
            
        # Create anchor link
        anchor = title.lower().replace(' ', '-')
        anchor = re.sub(r'[^\w-]', '', anchor)
        
        # Calculate indentation level
        indent = '  ' * (len(level) - 1)
        
        # Add to TOC
        toc_lines.append(f"{indent}- [{title}](#{anchor})")
    
    return '\n'.join(toc_lines)


def add_table_of_contents(markdown_content):
    """
    Add a table of contents to markdown content.
    
    Args:
        markdown_content: Markdown content to modify
        
    Returns:
        str: Markdown content with TOC added
    """
    toc = create_table_of_contents(markdown_content)
    
    # Find the first heading
    first_heading_match = re.search(r'^# ', markdown_content, re.MULTILINE)
    
    if first_heading_match:
        # Insert TOC after the first heading and its content
        heading_end = first_heading_match.end()
        next_heading_match = re.search(r'^# ', markdown_content[heading_end:], re.MULTILINE)
        
        if next_heading_match:
            insert_point = heading_end + next_heading_match.start()
            return markdown_content[:insert_point] + '\n\n' + toc + '\n\n' + markdown_content[insert_point:]
        else:
            # If no second heading, add after the content of the first section
            return markdown_content + '\n\n' + toc
    else:
        # If no headings, add to the beginning
        return toc + '\n\n' + markdown_content


def clean_markdown(markdown_content):
    """
    Clean up markdown content for better readability.
    
    Args:
        markdown_content: Markdown content to clean
        
    Returns:
        str: Cleaned markdown content
    """
    # Fix multiple consecutive blank lines
    cleaned = re.sub(r'\n{3,}', '\n\n', markdown_content)
    
    # Fix bullet list formatting
    cleaned = re.sub(r'^(\s*)-\s*', r'\1- ', cleaned, flags=re.MULTILINE)
    
    # Fix numbered list formatting
    cleaned = re.sub(r'^(\s*)\d+\.\s*', r'\1. ', cleaned, flags=re.MULTILINE)
    
    # Fix heading spacing
    cleaned = re.sub(r'^(#+)([^ ])', r'\1 \2', cleaned, flags=re.MULTILINE)
    
    # Ensure blank line before headings
    cleaned = re.sub(r'([^\n])\n(#+) ', r'\1\n\n\2 ', cleaned)
    
    # Ensure blank line after headings
    cleaned = re.sub(r'^(#+) (.+)$([^\n])', r'\1 \2\n\n\3', cleaned, flags=re.MULTILINE)
    
    return cleaned
