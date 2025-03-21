#!/usr/bin/env python3
"""
Content extraction module.

This module contains functions for extracting content from web pages,
including keyword searching and context extraction.
"""

import re
from bs4 import BeautifulSoup


def extract_context(text, keyword):
    """
    Extract sentence containing keyword and surrounding sentences.
    
    Args:
        text: Text to search in
        keyword: Keyword to find context for
        
    Returns:
        str: Context around the keyword
    """
    # Define regex pattern to split text into sentences
    sentence_pattern = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<!\d\.)(?<=\.|\?|\!)\s+(?=[A-Z0-9])')
    
    # Clean the text (remove excessive whitespace and newlines)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Split text into sentences
    sentences = sentence_pattern.split(text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    # Find the sentence containing the keyword
    keyword_sentences = []
    keyword_indices = []
    
    for i, sentence in enumerate(sentences):
        if re.search(r'\b' + re.escape(keyword) + r'\b', sentence, re.IGNORECASE):
            keyword_sentences.append(sentence)
            keyword_indices.append(i)
    
    if not keyword_sentences:
        return ""
    
    # Use the first occurrence if multiple exist
    keyword_sentence = keyword_sentences[0]
    keyword_index = keyword_indices[0]
    
    # Get previous and next sentences if they exist
    prev_sentence = sentences[keyword_index - 1] if keyword_index > 0 else ""
    next_sentence = sentences[keyword_index + 1] if keyword_index < len(sentences) - 1 else ""
    
    # Combine the context
    context = f"{prev_sentence} {keyword_sentence} {next_sentence}".strip()
    
    return context


def search_page_for_keywords(driver, url, keywords, content_filter):
    """
    Search a page for keywords and return the results with deduplication.
    
    Args:
        driver: Selenium WebDriver instance
        url: URL of the page being searched
        keywords: List of keywords to search for
        content_filter: ContentFilter instance
        
    Returns:
        list: List of [url, keyword, context] entries for found keywords
    """
    results = []
    seen_entries = set()  # Track unique (url, keyword, context) combinations
    
    try:
        # Get the page source after JavaScript execution
        page_content = driver.page_source
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(page_content, 'html.parser')
        
        # Apply content filtering by removing excluded elements
        excluded_selectors = content_filter.get_excluded_selectors()
        for selector in excluded_selectors:
            for element in soup.select(selector):
                element.decompose()
        
        # Extract all text elements
        text_elements = soup.find_all(['p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'span'])
        
        # Filter out empty or very short text elements
        text_elements = [el for el in text_elements if el.get_text(strip=True) and len(el.get_text(strip=True)) > 1]
        
        # Get text content
        page_text = ' '.join([element.get_text(strip=True) for element in text_elements])
        
        # Search for each keyword
        for keyword in keywords:
            # Find all occurrences of the keyword
            pattern = re.compile(r'\b' + re.escape(keyword) + r'\b', re.IGNORECASE)
            for match in pattern.finditer(page_text):
                # Get context around the keyword
                start = max(0, match.start() - 300)
                end = min(len(page_text), match.end() + 300)
                
                # Extract text chunk around the keyword
                text_chunk = page_text[start:end]
                
                # Extract the sentence context
                context = extract_context(text_chunk, keyword)
                
                # Skip empty contexts or those that don't actually contain the keyword
                if not context or not pattern.search(context):
                    continue
                
                # Create an entry tuple for deduplication check
                entry = (url, keyword, context)
                
                # Add to results only if we haven't seen this combination before
                if entry not in seen_entries:
                    seen_entries.add(entry)
                    results.append(list(entry))
                
        return results
            
    except Exception as e:
        print(f"Error searching for keywords on {url}: {e}")
        return []


def extract_structured_data(soup):
    """
    Extract structured data (JSON-LD, microdata) from the page.
    
    Args:
        soup: BeautifulSoup object of the page
        
    Returns:
        dict: Dictionary containing structured data
    """
    structured_data = {}
    
    # Extract JSON-LD
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    if json_ld_scripts:
        structured_data['json_ld'] = [script.string for script in json_ld_scripts if script.string]
    
    # Extract Open Graph metadata
    og_data = {}
    for meta in soup.find_all('meta', property=re.compile('^og:')):
        property_name = meta.get('property', '').replace('og:', '')
        if property_name:
            og_data[property_name] = meta.get('content', '')
    
    if og_data:
        structured_data['open_graph'] = og_data
    
    # Extract Twitter card metadata
    twitter_data = {}
    for meta in soup.find_all('meta', attrs={'name': re.compile('^twitter:')}):
        property_name = meta.get('name', '').replace('twitter:', '')
        if property_name:
            twitter_data[property_name] = meta.get('content', '')
    
    if twitter_data:
        structured_data['twitter_card'] = twitter_data
    
    # Extract microdata using itemscope and itemprop
    microdata = {}
    for element in soup.find_all(itemscope=True):
        itemtype = element.get('itemtype', '')
        if not itemtype:
            continue
            
        # Get simplified type name from URL
        type_name = itemtype.split('/')[-1] if '/' in itemtype else itemtype
        
        # Extract properties
        properties = {}
        for prop in element.find_all(itemprop=True):
            prop_name = prop.get('itemprop', '')
            
            # Get property value based on tag type
            if prop.name == 'meta':
                prop_value = prop.get('content', '')
            elif prop.name == 'link':
                prop_value = prop.get('href', '')
            elif prop.name == 'img':
                prop_value = prop.get('src', '')
            elif prop.name == 'time':
                prop_value = prop.get('datetime', '') or prop.text.strip()
            else:
                prop_value = prop.text.strip()
                
            if prop_name and prop_value:
                properties[prop_name] = prop_value
                
        if properties:
            if type_name not in microdata:
                microdata[type_name] = []
            microdata[type_name].append(properties)
    
    if microdata:
        structured_data['microdata'] = microdata
    
    return structured_data


def extract_list_items(soup):
    """
    Extract all list items from the page.
    
    Args:
        soup: BeautifulSoup object of the page
        
    Returns:
        dict: Dictionary containing lists by type
    """
    lists = {
        'unordered': [],
        'ordered': [],
        'definition': []
    }
    
    # Extract unordered lists
    for ul in soup.find_all('ul'):
        items = [li.get_text(strip=True) for li in ul.find_all('li') if li.get_text(strip=True)]
        if items:
            lists['unordered'].append(items)
    
    # Extract ordered lists
    for ol in soup.find_all('ol'):
        items = [li.get_text(strip=True) for li in ol.find_all('li') if li.get_text(strip=True)]
        if items:
            lists['ordered'].append(items)
    
    # Extract definition lists
    for dl in soup.find_all('dl'):
        items = []
        for dt, dd in zip(dl.find_all('dt'), dl.find_all('dd')):
            term = dt.get_text(strip=True)
            definition = dd.get_text(strip=True)
            if term and definition:
                items.append({'term': term, 'definition': definition})
        if items:
            lists['definition'].append(items)
    
    return lists
