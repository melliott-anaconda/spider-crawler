import time

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
    
def dismiss_cookie_consent_banner(browser):
    """
    Find cookie consent banner by locating accept buttons,
    then remove the entire banner (which is typically a direct child of body).
    
    Args:
        browser: Browser instance (Selenium or Playwright)
        
    Returns:
        bool: True if banner was found and removed
    """
    # Allow time for cookie banner to appear
    time.sleep(0.5)
    
    # Common cookie accept button selectors
    accept_button_selectors = [
        "[id*='accept']", "[class*='accept']",
        "button:contains('Accept')", "button:contains('Accept All')",
        "button:contains('I Accept')", "button:contains('OK')",
        "button:contains('Agree')", "button:contains('Got it')",
        "[id*='cookie'] button", "[class*='cookie'] button"
    ]
    
    try:
        if hasattr(browser, 'evaluate'):  # Playwright
            # Direct script to find and remove the banner
            result = browser.evaluate("""
                () => {
                    // Common button selectors that indicate cookie banners
                    const selectors = [
                        "[id*='accept']", "[class*='accept']",
                        "button:contains('Accept')", "button:contains('Accept All')",
                        "button:contains('I Accept')", "button:contains('OK')",
                        "button:contains('Agree')", "button:contains('Got it')",
                        "[id*='cookie'] button", "[class*='cookie'] button"
                    ];
                    
                    // Try to find a cookie accept button
                    let button = null;
                    for (const selector of selectors) {
                        try {
                            const element = document.querySelector(selector);
                            if (element && element.offsetParent !== null) {
                                button = element;
                                break;
                            }
                        } catch (e) {
                            continue;
                        }
                    }
                    
                    if (!button) return false;
                    
                    // Find the top-level container (direct child of body)
                    let container = button;
                    while (container.parentElement && container.parentElement !== document.body) {
                        container = container.parentElement;
                    }
                    
                    // Remove the container if it's a direct child of body
                    if (container.parentElement === document.body) {
                        container.remove();
                        return true;
                    }
                    
                    // Fallback: remove first fixed/absolute position parent
                    container = button;
                    while (container.parentElement) {
                        const style = window.getComputedStyle(container);
                        if (style.position === 'fixed' || style.position === 'absolute') {
                            container.remove();
                            return true;
                        }
                        container = container.parentElement;
                    }
                    
                    return false;
                }
            """)
            
            if result:
                print("Successfully removed cookie banner")
                return True
                
        else:  # Selenium
            # Direct script to find and remove the banner
            result = browser.execute_script("""
                // Common button selectors that indicate cookie banners
                const selectors = [
                    "[id*='accept']", "[class*='accept']", 
                    "button:contains('Accept')", "button:contains('Accept All')",
                    "button:contains('I Accept')", "button:contains('OK')",
                    "button:contains('Agree')", "button:contains('Got it')",
                    "[id*='cookie'] button", "[class*='cookie'] button"
                ];
                
                // Try to find a cookie accept button
                let button = null;
                for (const selector of selectors) {
                    try {
                        const elements = document.querySelectorAll(selector);
                        for (const element of elements) {
                            if (element && element.offsetParent !== null) {
                                button = element;
                                break;
                            }
                        }
                        if (button) break;
                    } catch (e) {
                        continue;
                    }
                }
                
                if (!button) return false;
                
                // Find the top-level container (direct child of body)
                let container = button;
                while (container.parentElement && container.parentElement !== document.body) {
                    container = container.parentElement;
                }
                
                // Remove the container if it's a direct child of body
                if (container.parentElement === document.body) {
                    container.remove();
                    return true;
                }
                
                // Fallback: remove first fixed/absolute position parent
                container = button;
                while (container.parentElement) {
                    const style = window.getComputedStyle(container);
                    if (style.position === 'fixed' || style.position === 'absolute') {
                        container.remove();
                        return true;
                    }
                    container = container.parentElement;
                }
                
                return false;
            """)
            
            if result:
                print("Successfully removed cookie banner")
                return True
        
        return False
        
    except Exception as e:
        print(f"Error removing cookie banner: {e}")
        return False
    
def remove_cookie_preference_center(browser):
    """
    Find and remove cookie preference center from the DOM.
    This removes the hidden cookie preference data even after the banner is dismissed.
    
    Args:
        browser: Browser instance (Selenium or Playwright)
        
    Returns:
        bool: True if preference center was found and removed
    """
    
    try:
        if hasattr(browser, 'evaluate'):  # Playwright
            # Direct script to find and remove the preference center
            result = browser.evaluate("""
                () => {
                    // Keywords that indicate cookie preference centers
                    const preferenceKeywords = [
                        'cookieyes', 'cookie-preferences', 'cookie-settings', 
                        'cookie-choices', 'consent-preferences', 'consent-manager',
                        'privacy-manager', 'privacy-preferences', 'gdpr-preferences',
                        'cookieconsent', 'cookie-law', 'cookie-control', 
                        'cookie-compliance', 'cookie-policy', 'cookie-notice',
                        'privacy-center', 'consent-options', 'cookie-details'
                    ];
                    
                    // Find elements containing these keywords in their id, class, or data attributes
                    const potentialElements = [];
                    
                    // Check elements with matching IDs or classes
                    for (const keyword of preferenceKeywords) {
                        // Look for ID matches
                        const idElement = document.getElementById(keyword) || 
                                         document.querySelector(`[id*="${keyword}"]`);
                        if (idElement) potentialElements.push(idElement);
                        
                        // Look for class matches
                        const classElements = document.querySelectorAll(`[class*="${keyword}"]`);
                        for (const el of classElements) potentialElements.push(el);
                        
                        // Look for data attribute matches
                        const dataElements = document.querySelectorAll(`[data-*="${keyword}"]`);
                        for (const el of dataElements) potentialElements.push(el);
                    }
                    
                    // Check for common cookie preference center containers
                    const commonSelectors = [
                        '#cookieYes', '.cookieyes', '#cookieChoices', '.cookie-preferences',
                        '#gdprContainer', '.gdpr-container', '#cookieConsent', '.cookie-consent',
                        '#cookiePreferences', '.cookie-preference', '#cookieSettings', '.cookie-settings',
                        '#consentManager', '.consent-manager', '#cookieControl', '.cookie-control'
                    ];
                    
                    for (const selector of commonSelectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) potentialElements.push(el);
                    }
                    
                    // Check elements with text content about cookies/privacy
                    const divElements = document.querySelectorAll('div');
                    for (const div of divElements) {
                        const text = div.innerText ? div.innerText.toLowerCase() : '';
                        if ((text.includes('cookie') || text.includes('privacy') || 
                             text.includes('gdpr') || text.includes('consent')) && 
                            (text.includes('preference') || text.includes('settings') || 
                             text.includes('choices') || text.includes('options'))) {
                            potentialElements.push(div);
                        }
                    }
                    
                    // Process each potential element
                    for (const element of potentialElements) {
                        if (!element || !element.parentElement) continue;
                        
                        // Find the top-level container (direct child of body)
                        let container = element;
                        while (container.parentElement && container.parentElement !== document.body) {
                            container = container.parentElement;
                        }
                        
                        // Remove the container if it's a direct child of body
                        if (container.parentElement === document.body) {
                            container.remove();
                            return true;
                        }
                    }
                    
                    // Fallback: look specifically for cookie preference modals/dialogs
                    const modalSelectors = [
                        'div[role="dialog"]', '.modal', '.dialog', '#cookie-modal', 
                        '.cookie-modal', '.consent-modal', '#gdpr-modal'
                    ];
                    
                    for (const selector of modalSelectors) {
                        const elements = document.querySelectorAll(selector);
                        for (const el of elements) {
                            const text = el.innerText ? el.innerText.toLowerCase() : '';
                            if (text.includes('cookie') || text.includes('privacy') || 
                                text.includes('gdpr') || text.includes('consent')) {
                                el.remove();
                                return true;
                            }
                        }
                    }
                    
                    return false;
                }
            """)
            
            if result:
                print("Successfully removed cookie preference center")
                return True
                
        else:  # Selenium
            # Direct script to find and remove the preference center
            result = browser.execute_script("""
                // Keywords that indicate cookie preference centers
                const preferenceKeywords = [
                    'cookieyes', 'cookie-preferences', 'cookie-settings', 
                    'cookie-choices', 'consent-preferences', 'consent-manager',
                    'privacy-manager', 'privacy-preferences', 'gdpr-preferences',
                    'cookieconsent', 'cookie-law', 'cookie-control', 
                    'cookie-compliance', 'cookie-policy', 'cookie-notice',
                    'privacy-center', 'consent-options', 'cookie-details'
                ];
                
                // Find elements containing these keywords in their id, class, or data attributes
                const potentialElements = [];
                
                // Check elements with matching IDs or classes
                for (const keyword of preferenceKeywords) {
                    // Look for ID matches
                    const idElement = document.getElementById(keyword) || 
                                     document.querySelector(`[id*="${keyword}"]`);
                    if (idElement) potentialElements.push(idElement);
                    
                    // Look for class matches
                    const classElements = document.querySelectorAll(`[class*="${keyword}"]`);
                    for (const el of classElements) potentialElements.push(el);
                    
                    // Look for data attribute matches
                    const dataElements = document.querySelectorAll(`[data-*="${keyword}"]`);
                    for (const el of dataElements) potentialElements.push(el);
                }
                
                // Check for common cookie preference center containers
                const commonSelectors = [
                    '#cookieYes', '.cookieyes', '#cookieChoices', '.cookie-preferences',
                    '#gdprContainer', '.gdpr-container', '#cookieConsent', '.cookie-consent',
                    '#cookiePreferences', '.cookie-preference', '#cookieSettings', '.cookie-settings',
                    '#consentManager', '.consent-manager', '#cookieControl', '.cookie-control'
                ];
                
                for (const selector of commonSelectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) potentialElements.push(el);
                }
                
                // Check elements with text content about cookies/privacy
                const divElements = document.querySelectorAll('div');
                for (const div of divElements) {
                    const text = div.innerText ? div.innerText.toLowerCase() : '';
                    if ((text.includes('cookie') || text.includes('privacy') || 
                         text.includes('gdpr') || text.includes('consent')) && 
                        (text.includes('preference') || text.includes('settings') || 
                         text.includes('choices') || text.includes('options'))) {
                        potentialElements.push(div);
                    }
                }
                
                // Process each potential element
                for (const element of potentialElements) {
                    if (!element || !element.parentElement) continue;
                    
                    // Find the top-level container (direct child of body)
                    let container = element;
                    while (container.parentElement && container.parentElement !== document.body) {
                        container = container.parentElement;
                    }
                    
                    // Remove the container if it's a direct child of body
                    if (container.parentElement === document.body) {
                        container.remove();
                        return true;
                    }
                }
                
                // Fallback: look specifically for cookie preference modals/dialogs
                const modalSelectors = [
                    'div[role="dialog"]', '.modal', '.dialog', '#cookie-modal', 
                    '.cookie-modal', '.consent-modal', '#gdpr-modal'
                ];
                
                for (const selector of modalSelectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {
                        const text = el.innerText ? el.innerText.toLowerCase() : '';
                        if (text.includes('cookie') || text.includes('privacy') || 
                            text.includes('gdpr') || text.includes('consent')) {
                            el.remove();
                            return true;
                        }
                    }
                }
                
                return false;
            """)
            
            if result:
                print("Successfully removed cookie preference center")
                return True
        
        return False
        
    except Exception as e:
        print(f"Error removing cookie preference center: {e}")
        return False
    
def clean_cookie_elements(browser):
    """
    Remove all cookie-related elements from the page:
    1. Cookie consent banners
    2. Cookie preference centers
    
    Args:
        browser: Browser instance (Selenium or Playwright)
        
    Returns:
        int: Number of elements removed (0, 1, or 2)
    """
    removed_count = 0
    
    # First remove the banner
    if dismiss_cookie_consent_banner(browser):
        removed_count += 1
    
    # Then remove the preference center
    if remove_cookie_preference_center(browser):
        removed_count += 1
    
    return removed_count