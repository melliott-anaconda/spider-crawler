#!/usr/bin/env python3
"""
HTML content parsing module.

This module contains functions for parsing and analyzing HTML content,
including page categorization and structure analysis.
"""

import re
from urllib.parse import urlparse


def determine_page_category(soup, url):
    """
    Attempts to categorize a webpage based on content and URL patterns.

    Args:
        soup: BeautifulSoup object of the page
        url: URL of the page

    Returns:
        str: Category name (products, solutions, documentation, blog, faq, help, or misc)
    """
    path = urlparse(url).path.lower()

    # URL-based categorization
    if any(segment in path for segment in ["/product", "/products"]):
        return "products"
    elif any(segment in path for segment in ["/solution", "/solutions"]):
        return "solutions"
    elif any(
        segment in path
        for segment in [
            "/doc",
            "/docs",
            "/documentation",
            "/guide",
            "/guides",
            "/manual",
        ]
    ):
        return "documentation"
    elif any(
        segment in path for segment in ["/blog", "/news", "/article", "/articles"]
    ):
        return "blog"
    elif any(
        segment in path for segment in ["/faq", "/faqs", "/question", "/questions"]
    ):
        return "faq"
    elif any(segment in path for segment in ["/help", "/support", "/troubleshoot"]):
        return "help"

    # Content-based categorization
    text_content = soup.get_text().lower()

    # Count occurrences of category-related terms
    category_terms = {
        "products": [
            "product",
            "feature",
            "capability",
            "buy",
            "purchase",
            "pricing",
            "edition",
            "license",
        ],
        "solutions": [
            "solution",
            "service",
            "approach",
            "methodology",
            "framework",
            "platform",
            "integrate",
        ],
        "documentation": [
            "documentation",
            "guide",
            "reference",
            "manual",
            "tutorial",
            "instruction",
            "implementation",
        ],
        "blog": [
            "blog",
            "post",
            "article",
            "news",
            "update",
            "published",
            "author",
            "date",
        ],
        "faq": [
            "faq",
            "question",
            "answer",
            "frequently asked",
            "common question",
            "troubleshoot",
        ],
        "help": [
            "help",
            "support",
            "contact us",
            "assistance",
            "ticket",
            "troubleshoot",
        ],
    }

    # Count occurrences of category terms
    category_scores = {}
    for category, terms in category_terms.items():
        score = sum(text_content.count(term) for term in terms)
        category_scores[category] = score

    # Check for h1/h2 headers that might indicate category
    headers = [h.get_text().lower() for h in soup.find_all(["h1", "h2"])]
    for header in headers:
        for category, terms in category_terms.items():
            if any(term in header for term in terms):
                category_scores[category] += 5  # Give extra weight to header matches

    # Get the category with the highest score
    max_category = (
        max(category_scores.items(), key=lambda x: x[1])
        if category_scores
        else ("misc", 0)
    )

    # Only use content-based category if the score is significant
    if max_category[1] > 5:
        return max_category[0]

    # Default to misc if no strong category detected
    return "misc"
