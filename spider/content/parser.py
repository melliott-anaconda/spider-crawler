#!/usr/bin/env python3
"""
HTML content parsing module.

This module contains functions for parsing and analyzing HTML content,
including page categorization and structure analysis.
"""

from urllib.parse import urlparse
from collections import Counter
import re


def determine_page_category(soup, url):
    """
    Attempts to categorize a webpage based on content and URL patterns.
    
    Args:
        soup: BeautifulSoup object of the page
        url: URL of the page
        
    Returns:
        str: Category name (products, solutions, documentation, blog, faq, help, or misc)
    """
    url_lower = url.lower()
    path = urlparse(url).path.lower()
    
    # URL-based categorization
    if any(segment in path for segment in ['/product', '/products']):
        return 'products'
    elif any(segment in path for segment in ['/solution', '/solutions']):
        return 'solutions'
    elif any(segment in path for segment in ['/doc', '/docs', '/documentation', '/guide', '/guides', '/manual']):
        return 'documentation'
    elif any(segment in path for segment in ['/blog', '/news', '/article', '/articles']):
        return 'blog'
    elif any(segment in path for segment in ['/faq', '/faqs', '/question', '/questions']):
        return 'faq'
    elif any(segment in path for segment in ['/help', '/support', '/troubleshoot']):
        return 'help'
    
    # Content-based categorization
    text_content = soup.get_text().lower()
    
    # Count occurrences of category-related terms
    category_terms = {
        'products': ['product', 'feature', 'capability', 'buy', 'purchase', 'pricing', 'edition', 'license'],
        'solutions': ['solution', 'service', 'approach', 'methodology', 'framework', 'platform', 'integrate'],
        'documentation': ['documentation', 'guide', 'reference', 'manual', 'tutorial', 'instruction', 'implementation'],
        'blog': ['blog', 'post', 'article', 'news', 'update', 'published', 'author', 'date'],
        'faq': ['faq', 'question', 'answer', 'frequently asked', 'common question', 'troubleshoot'],
        'help': ['help', 'support', 'contact us', 'assistance', 'ticket', 'troubleshoot']
    }
    
    # Count occurrences of category terms
    category_scores = {}
    for category, terms in category_terms.items():
        score = sum(text_content.count(term) for term in terms)
        category_scores[category] = score
    
    # Check for h1/h2 headers that might indicate category
    headers = [h.get_text().lower() for h in soup.find_all(['h1', 'h2'])]
    for header in headers:
        for category, terms in category_terms.items():
            if any(term in header for term in terms):
                category_scores[category] += 5  # Give extra weight to header matches
    
    # Get the category with the highest score
    max_category = max(category_scores.items(), key=lambda x: x[1]) if category_scores else ('misc', 0)
    
    # Only use content-based category if the score is significant
    if max_category[1] > 5:
        return max_category[0]
    
    # Default to misc if no strong category detected
    return 'misc'


def extract_headings(soup):
    """
    Extract headings from the page in hierarchical order.
    
    Args:
        soup: BeautifulSoup object of the page
        
    Returns:
        list: List of dictionaries with heading text, level, and ID
    """
    headings = []
    
    for level in range(1, 7):  # h1 through h6
        for heading in soup.find_all(f'h{level}'):
            heading_text = heading.get_text(strip=True)
            
            # Skip empty headings
            if not heading_text:
                continue
                
            # Get heading ID if available
            heading_id = heading.get('id', '')
            
            # If no ID, look for closest element with ID
            if not heading_id:
                parent_with_id = heading.find_parent(id=True)
                if parent_with_id:
                    heading_id = parent_with_id.get('id', '')
            
            headings.append({
                'text': heading_text,
                'level': level,
                'id': heading_id
            })
    
    return headings


def extract_meta_data(soup, url):
    """
    Extract metadata from the page such as title, description, etc.
    
    Args:
        soup: BeautifulSoup object of the page
        url: URL of the page
        
    Returns:
        dict: Dictionary containing metadata
    """
    metadata = {
        'url': url,
        'title': soup.title.string.strip() if soup.title else '',
        'domain': urlparse(url).netloc
    }
    
    # Extract meta description
    description_tag = soup.find('meta', attrs={'name': 'description'})
    if description_tag:
        metadata['description'] = description_tag.get('content', '')
    
    # Extract meta keywords
    keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
    if keywords_tag:
        metadata['keywords'] = keywords_tag.get('content', '')
    
    # Extract canonical URL
    canonical_tag = soup.find('link', attrs={'rel': 'canonical'})
    if canonical_tag:
        metadata['canonical'] = canonical_tag.get('href', '')
    
    # Extract author
    author_tag = soup.find('meta', attrs={'name': 'author'})
    if author_tag:
        metadata['author'] = author_tag.get('content', '')
    
    # Extract publication date
    date_tags = [
        soup.find('meta', attrs={'property': 'article:published_time'}),
        soup.find('meta', attrs={'name': 'date'}),
        soup.find('time')
    ]
    
    for tag in date_tags:
        if tag:
            if tag.name == 'meta':
                metadata['date'] = tag.get('content', '')
            else:
                metadata['date'] = tag.get('datetime', '') or tag.text.strip()
            break
    
    return metadata


def get_page_content_stats(soup):
    """
    Analyze page content and return statistics.
    
    Args:
        soup: BeautifulSoup object of the page
        
    Returns:
        dict: Statistics about the page content
    """
    # Get all text
    text = soup.get_text(separator=' ', strip=True)
    words = re.findall(r'\b\w+\b', text.lower())
    
    # Count word frequencies
    word_freq = Counter(words)
    
    # Count links
    links = soup.find_all('a', href=True)
    internal_links = 0
    external_links = 0
    
    for link in links:
        href = link.get('href', '')
        if href.startswith('#') or not href:
            continue  # Skip anchors and empty links
        elif href.startswith('http') and urlparse(href).netloc != urlparse(soup.get('url', '')).netloc:
            external_links += 1
        else:
            internal_links += 1
    
    # Count images
    images = len(soup.find_all('img'))
    
    # Get stats
    stats = {
        'word_count': len(words),
        'sentence_count': len(re.split(r'[.!?]+', text)),
        'paragraph_count': len(soup.find_all(['p'])),
        'heading_count': len(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])),
        'link_count': len(links),
        'internal_links': internal_links,
        'external_links': external_links,
        'image_count': images,
        'most_common_words': dict(word_freq.most_common(10)),
        'readability': calculate_readability(text)
    }
    
    return stats


def calculate_readability(text):
    """
    Calculate readability metrics for text.
    
    Args:
        text: Text to analyze
        
    Returns:
        dict: Readability metrics
    """
    # Simplified readability calculation
    words = re.findall(r'\b\w+\b', text.lower())
    sentences = re.split(r'[.!?]+', text)
    
    if not sentences or not words:
        return {'score': 0, 'level': 'Unknown'}
    
    # Average words per sentence
    avg_words_per_sentence = len(words) / len(sentences)
    
    # Average word length
    avg_word_length = sum(len(word) for word in words) / len(words)
    
    # Simple readability score (higher = more complex)
    score = (avg_words_per_sentence * 0.39) + (avg_word_length * 5.8) - 15.59
    
    # Determine reading level
    if score < 30:
        level = 'Very Easy'
    elif score < 50:
        level = 'Easy'
    elif score < 60:
        level = 'Moderate'
    elif score < 70:
        level = 'Difficult'
    else:
        level = 'Very Difficult'
    
    return {
        'score': round(score, 1),
        'words_per_sentence': round(avg_words_per_sentence, 1),
        'avg_word_length': round(avg_word_length, 1),
        'level': level
    }
