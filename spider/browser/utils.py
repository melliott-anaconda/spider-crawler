def execute_browser_script(browser, script, *args):
    """
    Execute JavaScript in a browser, handling differences between Selenium and Playwright.
    
    Args:
        browser: Browser instance (Selenium WebDriver or Playwright Page)
        script: JavaScript code to execute
        *args: Arguments to pass to the script
        
    Returns:
        The result of the script execution
    """
    if hasattr(browser, 'evaluate'):
        # Playwright-style execution
        return browser.evaluate(script, *args)
    elif hasattr(browser, 'execute_script'):
        # Selenium-style execution
        return browser.execute_script(script, *args)
    else:
        raise TypeError("Browser object doesn't support JavaScript execution")