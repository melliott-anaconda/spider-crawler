#!/usr/bin/env python3
"""
URL handling and normalization module.

This module contains functions for processing, normalizing, and validating URLs,
as well as extracting links from web pages.
"""

import json
import os
import urllib.parse
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from ..browser.navigator import hash_page_content


def normalize_url(url, keep_fragments=False, keep_query=True):
    """
    Normalize a URL to avoid duplicates.

    Args:
        url: The URL to normalize
        keep_fragments: Whether to keep URL fragments (#)
        keep_query: Whether to keep query parameters

    Returns:
        str: Normalized URL
    """
    parsed = urllib.parse.urlparse(url)

    # Handle scheme and netloc (domain)
    normalized = f"{parsed.scheme}://{parsed.netloc}"

    # Handle path
    if parsed.path:
        # Ensure path starts with / and remove trailing /
        path = parsed.path if parsed.path.startswith("/") else "/" + parsed.path
        path = path[:-1] if path.endswith("/") and len(path) > 1 else path
        normalized += path
    else:
        normalized += "/"

    # Handle query parameters if requested
    if keep_query and parsed.query:
        normalized += f"?{parsed.query}"

    # Handle fragments if requested (important for SPAs)
    if keep_fragments and parsed.fragment:
        normalized += f"#{parsed.fragment}"

    return normalized


def is_webpage_url(url, allowed_extensions=None):
    """
    Check if the URL is likely to point to a webpage and not to a non-webpage resource.

    Args:
        url: URL to check
        allowed_extensions: Additional file extensions to allow

    Returns:
        bool: True if the URL is likely a webpage, False otherwise
    """
    # Default webpage extensions
    webpage_extensions = {
        ".html",
        ".htm",
        ".php",
        ".asp",
        ".aspx",
        ".jsp",
        ".do",
        ".xhtml",
        ".shtml",
    }

    # Add allowed extensions if specified
    if allowed_extensions:
        webpage_extensions.update(allowed_extensions)

    # Parse the URL
    parsed_url = urllib.parse.urlparse(url)

    # URLs without file extensions are typically webpages (like example.com/about)
    path = parsed_url.path

    # If the URL has no path or ends with '/', it's likely a webpage
    if not path or path == "/" or path.endswith("/"):
        return True

    # Check for query parameters
    if parsed_url.query:
        return True  # URLs with query parameters are likely dynamic pages

    # Check for fragment (important for SPAs)
    if parsed_url.fragment:
        return True  # URLs with fragments are likely SPA routes

    # Extract the file extension (if any)
    _, ext = os.path.splitext(path)
    ext = ext.lower()

    # Common non-webpage extensions to exclude
    excluded_extensions = {
        # Static assets
        ".css",
        ".js",
        ".map",
        # Images
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".svg",
        ".webp",
        ".ico",
        ".tif",
        ".tiff",
        # Audio/Video
        ".mp3",
        ".wav",
        ".ogg",
        ".mp4",
        ".avi",
        ".mov",
        ".flv",
        ".wmv",
        ".webm",
        ".mkv",
        # Documents
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".txt",
        ".rtf",
        ".csv",
        ".xml",
        ".json",
        ".yaml",
        ".yml",
        # Archives
        ".zip",
        ".rar",
        ".tar",
        ".gz",
        ".7z",
        ".bz2",
        # Executables and binaries
        ".exe",
        ".dll",
        ".so",
        ".bin",
        ".apk",
        ".dmg",
        ".iso",
        ".msi",
        # Fonts
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".eot",
        # Other
        ".swf",
        ".dat",
    }

    # If the extension exists and is in the excluded list and not in the allowed list
    if ext and ext in excluded_extensions and ext not in webpage_extensions:
        return False

    # If the extension exists and is in the webpage list, it's a webpage
    if ext and ext in webpage_extensions:
        return True

    # If no extension or an unknown extension, let's consider it as potentially a webpage
    return True


def get_page_links(
    driver,
    url,
    base_domain,
    path_prefix=None,
    allow_subdomains=False,
    allowed_extensions=None,
):
    """
    Extract links from a page with domain/path matching.

    Args:
        driver: Selenium WebDriver instance
        url: Current URL
        base_domain: Base domain to restrict links to
        path_prefix: Path prefix to restrict links to
        allow_subdomains: Whether to allow links to subdomains
        allowed_extensions: Additional file extensions to allow

    Returns:
        set: Set of normalized URLs
    """
    links = set()

    try:
        # Parse the current URL to get the exact subdomain we're on
        parsed_current_url = urllib.parse.urlparse(url)
        current_exact_domain = parsed_current_url.netloc

        # Get all anchor tags
        a_elements = driver.find_elements(By.TAG_NAME, "a")

        # Extract href attributes
        for a in a_elements:
            try:
                href = a.get_attribute("href")
                if (
                    href
                    and not href.startswith("javascript:")
                    and not href.startswith("#")
                ):
                    # Normalize URL
                    full_url = href.split("#")[0].split("?")[0]
                    if full_url.endswith("/"):
                        full_url = full_url[:-1]

                    # Check if it's a webpage URL
                    if not is_webpage_url(full_url, allowed_extensions):
                        continue

                    # Check domain and path prefix
                    parsed_url = urllib.parse.urlparse(full_url)
                    link_domain = parsed_url.netloc

                    # Domain matching logic based on allow_subdomains flag
                    if allow_subdomains:
                        # Allow any subdomain of the base domain
                        base_domain_no_www = base_domain.replace("www.", "")
                        link_domain_no_www = link_domain.replace("www.", "")
                        domain_match = (
                            base_domain_no_www == link_domain_no_www
                            or link_domain_no_www.endswith("." + base_domain_no_www)
                        )
                    else:
                        # Stay on the exact same subdomain
                        # Handle www vs non-www as the same
                        current_domain_no_www = current_exact_domain.replace("www.", "")
                        link_domain_no_www = link_domain.replace("www.", "")
                        domain_match = current_domain_no_www == link_domain_no_www

                    if domain_match:
                        # If path_prefix is specified, check that the path starts with it
                        if path_prefix is None or parsed_url.path.startswith(
                            path_prefix
                        ):
                            links.add(full_url)
            except Exception as e:
                continue

        # Try using Beautiful Soup as a backup
        if len(links) < 3:
            try:
                soup = BeautifulSoup(driver.page_source, "html.parser")
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    if (
                        href
                        and not href.startswith("javascript:")
                        and not href.startswith("#")
                    ):
                        # Handle relative URLs
                        if not href.startswith("http"):
                            full_url = urllib.parse.urljoin(url, href)
                        else:
                            full_url = href

                        # Normalize URL
                        full_url = full_url.split("#")[0].split("?")[0]
                        if full_url.endswith("/"):
                            full_url = full_url[:-1]

                        # Check if it's a webpage URL
                        if not is_webpage_url(full_url, allowed_extensions):
                            continue

                        parsed_url = urllib.parse.urlparse(full_url)
                        link_domain = parsed_url.netloc

                        # Domain matching logic based on allow_subdomains flag
                        if allow_subdomains:
                            # Allow any subdomain of the base domain
                            base_domain_no_www = base_domain.replace("www.", "")
                            link_domain_no_www = link_domain.replace("www.", "")
                            domain_match = (
                                base_domain_no_www == link_domain_no_www
                                or link_domain_no_www.endswith("." + base_domain_no_www)
                            )
                        else:
                            # Stay on the exact same subdomain
                            # Handle www vs non-www as the same
                            current_domain_no_www = current_exact_domain.replace(
                                "www.", ""
                            )
                            link_domain_no_www = link_domain.replace("www.", "")
                            domain_match = current_domain_no_www == link_domain_no_www

                        if domain_match:
                            # If path_prefix is specified, check that the path starts with it
                            if path_prefix is None or parsed_url.path.startswith(
                                path_prefix
                            ):
                                links.add(full_url)
            except Exception as e:
                print(f"BeautifulSoup parsing error: {e}")

    except Exception as e:
        print(f"Error extracting links from {url}: {e}")

    print(f"Found {len(links)} valid links on {url}")
    return links


def get_spa_links(
    driver,
    url,
    base_domain,
    path_prefix=None,
    allow_subdomains=False,
    allowed_extensions=None,
):
    """
    Extract links from a page with support for SPAs.

    This function handles both traditional hyperlinks and clickable elements in SPAs.

    Args:
        driver: Selenium WebDriver instance
        url: Current URL
        base_domain: Base domain to restrict links to
        path_prefix: Path prefix to restrict links to
        allow_subdomains: Whether to allow links to subdomains
        allowed_extensions: Additional file extensions to allow

    Returns:
        set: Set of normalized URLs
    """
    links = set()
    clickable_elements = set()
    current_url_hash = hash_page_content(driver.page_source)

    try:
        # Parse the current URL
        parsed_current_url = urllib.parse.urlparse(url)
        current_exact_domain = parsed_current_url.netloc

        # PART 1: Get traditional <a> links
        a_elements = driver.find_elements(By.TAG_NAME, "a")

        for a in a_elements:
            try:
                href = a.get_attribute("href")
                if href and not href.startswith("javascript:"):
                    # Keep fragments for SPAs
                    full_url = normalize_url(href, keep_fragments=True)

                    # Check if it's a webpage URL
                    if not is_webpage_url(full_url, allowed_extensions):
                        continue

                    # Check domain
                    parsed_url = urllib.parse.urlparse(full_url)
                    link_domain = parsed_url.netloc

                    # Domain matching logic
                    if allow_subdomains:
                        base_domain_no_www = base_domain.replace("www.", "")
                        link_domain_no_www = link_domain.replace("www.", "")
                        domain_match = (
                            base_domain_no_www == link_domain_no_www
                            or link_domain_no_www.endswith("." + base_domain_no_www)
                        )
                    else:
                        current_domain_no_www = current_exact_domain.replace("www.", "")
                        link_domain_no_www = link_domain.replace("www.", "")
                        domain_match = current_domain_no_www == link_domain_no_www

                    if domain_match:
                        # Check path prefix
                        if path_prefix is None or parsed_url.path.startswith(
                            path_prefix
                        ):
                            links.add(full_url)
            except Exception as e:
                continue

        # PART 2: Find clickable elements that might be part of an SPA navigation system
        # Common selectors for clickable elements in SPAs
        spa_selectors = [
            # Navigation items
            "nav li",
            ".nav-item",
            ".navbar-item",
            ".menu-item",
            '[role="menuitem"]',
            # Buttons that might be used for navigation
            'button:not([type="submit"])',
            '[role="button"]',
            # Common interactive elements
            ".clickable",
            ".interactive",
            ".nav-link",
            # Tab-like navigation
            ".tab",
            ".tabs li",
            '[role="tab"]',
            # List items that might be clickable
            "ul.menu li",
            "ul.nav li",
            "ol.nav li",
        ]

        # Combine all selectors
        combined_selector = ", ".join(spa_selectors)

        # Find potentially clickable elements
        potential_elements = driver.find_elements(By.CSS_SELECTOR, combined_selector)

        # Filter for elements that look clickable but don't have href attributes
        for element in potential_elements:
            try:
                # Skip already processed <a> tags
                if element.tag_name == "a" and element.get_attribute("href"):
                    continue

                # Check if element is displayed and might be clickable
                if element.is_displayed() and element.is_enabled():
                    # Check if element has click handlers
                    has_click = driver.execute_script(
                        """
                        var elem = arguments[0];
                        var clickEvents = elem.onclick || 
                                         elem.getAttribute('onclick') ||
                                         elem.getAttribute('ng-click') ||
                                         elem.getAttribute('@click') ||
                                         elem.getAttribute('v-on:click') ||
                                         elem.getAttribute('data-click') ||
                                         elem.getAttribute('(click)');
                        return clickEvents !== null && clickEvents !== undefined;
                    """,
                        element,
                    )

                    # Elements with specific classes/attributes suggesting clickability
                    has_clickable_attr = driver.execute_script(
                        """
                        var elem = arguments[0];
                        return elem.classList.contains('clickable') || 
                               elem.classList.contains('button') ||
                               elem.getAttribute('role') === 'button' ||
                               elem.getAttribute('tabindex') === '0' ||
                               elem.tagName === 'BUTTON';
                    """,
                        element,
                    )

                    if has_click or has_clickable_attr:
                        # Get element info for identification
                        elem_info = {
                            "xpath": driver.execute_script(
                                """
                                function getPathTo(element) {
                                    if (element.id) return '//*[@id="' + element.id + '"]';
                                    if (element === document.body) return '/html/body';
                                    
                                    var index = 0;
                                    var siblings = element.parentNode.childNodes;
                                    for (var i = 0; i < siblings.length; i++) {
                                        var sibling = siblings[i];
                                        if (sibling === element) return getPathTo(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (index+1) + ']';
                                        if (sibling.nodeType === 1 && sibling.tagName === element.tagName) index++;
                                    }
                                }
                                return getPathTo(arguments[0]);
                            """,
                                element,
                            ),
                            "text": element.text,
                            "tag": element.tag_name,
                        }
                        clickable_elements.add(json.dumps(elem_info))
            except Exception as e:
                continue

        print(
            f"Found {len(links)} <a> links and {len(clickable_elements)} potential clickable elements on {url}"
        )

        # PART 3: Try clicking on identified clickable elements to discover SPA routes
        current_url = driver.current_url
        new_links = set()

        for i, elem_info_json in enumerate(clickable_elements):
            if i >= 15:  # Limit to prevent excessive clicking
                break

            elem_info = json.loads(elem_info_json)
            try:
                # Try to find the element
                element = driver.find_element(By.XPATH, elem_info["xpath"])

                if element.is_displayed() and element.is_enabled():
                    # Save current state
                    original_url = driver.current_url
                    original_hash = current_url_hash

                    # Click the element
                    actions = ActionChains(driver)
                    actions.move_to_element(element).click().perform()

                    # Wait for potential page changes
                    import time

                    time.sleep(1.5)  # Give SPA time to update the DOM

                    # Check if URL or content changed
                    new_url = driver.current_url
                    new_hash = hash_page_content(driver.page_source)

                    if new_url != original_url:
                        # URL changed - add as new link
                        normalized_url = normalize_url(new_url, keep_fragments=True)
                        new_links.add(normalized_url)
                    elif new_hash != original_hash:
                        # Content changed but URL didn't - SPA route change
                        # Use fragment identifier or create one based on clicked element
                        if "#" in new_url:
                            new_links.add(new_url)
                        else:
                            # Create identifier based on element text or position
                            identifier = elem_info.get("text", "").strip()
                            if not identifier:
                                identifier = f"section_{i}"
                            spa_url = (
                                f"{original_url}#{identifier.lower().replace(' ', '-')}"
                            )
                            new_links.add(spa_url)

                    # Navigate back to original state if needed
                    if new_url != original_url:
                        driver.get(original_url)
                        # Wait for page to load
                        time.sleep(1)
            except Exception as e:
                continue

        # Add newly discovered SPA links
        links.update(new_links)
        print(f"Discovered {len(new_links)} additional SPA routes")

        # PART 4: Fall back to BeautifulSoup for additional link extraction
        if len(links) < 5:  # If we found very few links, try parsing with BS4
            try:
                soup = BeautifulSoup(driver.page_source, "html.parser")
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    if (
                        href
                        and not href.startswith("javascript:")
                        and not href.startswith("#")
                    ):
                        # Handle relative URLs
                        if not href.startswith("http"):
                            full_url = urllib.parse.urljoin(url, href)
                        else:
                            full_url = href

                        # Keep fragments for SPAs
                        full_url = normalize_url(full_url, keep_fragments=True)

                        # Check if it's a webpage URL
                        if not is_webpage_url(full_url, allowed_extensions):
                            continue

                        parsed_url = urllib.parse.urlparse(full_url)
                        link_domain = parsed_url.netloc

                        # Domain matching logic based on allow_subdomains flag
                        if allow_subdomains:
                            base_domain_no_www = base_domain.replace("www.", "")
                            link_domain_no_www = link_domain.replace("www.", "")
                            domain_match = (
                                base_domain_no_www == link_domain_no_www
                                or link_domain_no_www.endswith("." + base_domain_no_www)
                            )
                        else:
                            current_domain_no_www = current_exact_domain.replace(
                                "www.", ""
                            )
                            link_domain_no_www = link_domain.replace("www.", "")
                            domain_match = current_domain_no_www == link_domain_no_www

                        if domain_match:
                            # If path_prefix is specified, check that the path starts with it
                            if path_prefix is None or parsed_url.path.startswith(
                                path_prefix
                            ):
                                links.add(full_url)
            except Exception as e:
                print(f"BeautifulSoup parsing error: {e}")

        # PART 5: Look for common SPA router patterns in JavaScript
        try:
            # Extract routes from common SPA frameworks (React Router, Vue Router, Angular Router)
            router_patterns = [
                # React Router
                r'path:\s*[\'"`](\/[^\'"`]*)[\'"`]',
                # Vue Router
                r'path:\s*[\'"`](\/[^\'"`]*)[\'"`]',
                # Angular Router
                r'path:\s*[\'"`]([^\'"`]*)[\'"`]',
                # General route patterns
                r'route\([\'"`](\/[^\'"`]*)[\'"`]',
                r'navigate\([\'"`](\/[^\'"`]*)[\'"`]',
            ]

            # Get all script content
            scripts = driver.find_elements(By.TAG_NAME, "script")
            for script in scripts:
                try:
                    # Get script content
                    script_content = script.get_attribute("innerHTML")
                    if not script_content:
                        continue

                    # Look for route patterns
                    import re

                    for pattern in router_patterns:
                        matches = re.findall(pattern, script_content)
                        for match in matches:
                            if match and len(match) > 1:  # Avoid single char routes
                                # Construct full URL with route
                                route_url = f"{parsed_current_url.scheme}://{parsed_current_url.netloc}{match}"
                                links.add(route_url)
                except:
                    continue

        except Exception as e:
            print(f"Error extracting routes from scripts: {e}")

    except Exception as e:
        print(f"Error extracting links from {url}: {e}")

    print(f"Found {len(links)} valid links on {url}")
    return links
