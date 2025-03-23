# Create browser/stealth.py
"""
Browser stealth configuration to avoid bot detection.
"""

try:
    from selenium_stealth import stealth
except ImportError:
    print("selenium-stealth not installed. For stealth mode, install with: pip install selenium-stealth")
    stealth = None

def apply_stealth_mode(driver):
    """
    Apply stealth mode to the WebDriver to avoid bot detection.
    
    Args:
        driver: Selenium WebDriver instance
        
    Returns:
        WebDriver: The modified WebDriver instance
    """
    if stealth is None:
        print("Warning: selenium-stealth not available, stealth mode not applied")
        return driver
        
    try:
        stealth(
            driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        print("Applied stealth mode to WebDriver")
        return driver
    except Exception as e:
        print(f"Warning: Could not apply stealth mode: {e}")
        return driver