# Create browser/undetected.py
"""
Undetected ChromeDriver setup for avoiding advanced bot detection.
"""


def setup_undetected_webdriver(headless=True, retry_count=3):
    """
    Set up and return an Undetected ChromeDriver instance.

    Args:
        headless: Whether to run in headless mode
        retry_count: Number of times to retry WebDriver creation

    Returns:
        WebDriver: Configured Undetected ChromeDriver instance

    Raises:
        RuntimeError: If WebDriver creation fails after specified retry attempts
    """
    try:
        import undetected_chromedriver as uc
    except ImportError:
        raise ImportError(
            "undetected-chromedriver not installed. Install with: pip install undetected-chromedriver"
        )

    import time

    for attempt in range(retry_count):
        try:
            # Set up options
            options = uc.ChromeOptions()
            if headless:
                options.add_argument("--headless=new")

            # Standard options
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")

            # Create driver
            driver = uc.Chrome(options=options)

            # Set timeouts
            driver.set_page_load_timeout(30)
            driver.set_script_timeout(30)

            print(f"Created undetected ChromeDriver (headless={headless})")
            return driver

        except Exception as e:
            print(
                f"Undetected ChromeDriver creation failed (attempt {attempt+1}/{retry_count}): {e}"
            )
            time.sleep(2)

            if attempt == retry_count - 1:
                raise

    raise RuntimeError(
        "Failed to create Undetected ChromeDriver after multiple attempts"
    )
