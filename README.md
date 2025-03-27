# Spider Crawler

A powerful, adaptive web crawler for keyword searching and content extraction with support for Single Page Applications (SPAs).

## Features

- **Keyword Search Mode**: Search websites for specific keywords and extract their context
- **Markdown Mode**: Extract and save website content as structured markdown files
- **Adaptive Rate Control**: Dynamically adjusts crawling speed to avoid overwhelming target servers
- **Checkpoint/Resume**: Save progress and resume crawling later
- **SPA Support**: Enhanced JavaScript handling for modern Single Page Applications
- **Parallel Processing**: Uses multiple workers for efficient crawling
- **Content Filtering**: Selectively include or exclude page elements like headers, menus, and footers
- **Domain Control**: Restrict crawling to specific subdomains or paths

## Installation

### Using Conda

```bash
conda install -c michael-elliott spider-crawler
```

### From Source

```bash
git clone https://github.com/melliott-anaconda/spider-crawler.git
cd spider-crawler
pip install -e .
```

## Dependencies

- Python 3.7+
- selenium
- beautifulsoup4
- html2text
- webdriver-manager

You'll also need Chrome browser installed for the crawler to work properly.

If you want to run in playwright mode, you will need to install playwright if conda install did not install it.
```bash
pip install playwright
python -m playwright install
```

## Quick Start

### Keyword Search Mode

Search a website for specific keywords:

```bash
spider https://example.com --keywords "important,topics,keywords"
```

The crawler will save results to a CSV file with the URL, keyword, and context for each match.

### Markdown Extraction Mode

Extract and save website content as markdown files:

```bash
spider https://example.com --markdown-mode
```

Files will be organized by category (documentation, blog, products, etc.) in a directory structure.

## Advanced Usage

### Configuration File

You can save and load configuration:

```bash
# Save configuration
spider https://example.com --keywords "important,topics" --save-config my_config.json

# Load configuration
spider --config my_config.json
```

### SPA Mode

For modern JavaScript-heavy websites:

```bash
spider https://example.com --keywords "important,topics" --spa
```

### Rate Control

Customize crawling speed:

```bash
spider https://example.com --keywords "important,topics" --max-workers 6 --min-delay 1.0 --initial-delay 2.0
```

### Domain Restrictions

```bash
# Restrict to a specific path
spider https://example.com --keywords "important,topics" --path-prefix "/docs/"

# Allow crawling across subdomains
spider https://example.com --keywords "important,topics" --allow-subdomains
```

### Content Filtering

```bash
# Include specific page elements
spider https://example.com --keywords "important,topics" --include-headers --include-menus

# Exclude custom elements
spider https://example.com --keywords "important,topics" --exclude-selectors ".ads,.comments,#sidebar"
```

## Command-Line Options

### Basic Options

- `url`: Starting URL to spider from
- `--keywords TEXT`: Comma-separated list of keywords to search for
- `--output FILE`: Output CSV file path
- `--max-pages N`: Maximum number of pages to spider
- `--path-prefix TEXT`: Path prefix to restrict crawling to

### Browser Options

- `--visible`: Run in visible browser mode
- `--webdriver-path PATH`: Path to the webdriver executable

### Checkpoint Options

- `--resume`: Resume from checkpoint if available
- `--max-restarts N`: Maximum number of WebDriver restarts
- `--checkpoint-interval N`: Minutes between checkpoints

### Rate Control Options

- `--max-workers N`: Maximum parallel workers
- `--min-workers N`: Minimum parallel workers
- `--min-delay FLOAT`: Minimum delay between requests
- `--max-delay FLOAT`: Maximum delay between requests
- `--initial-delay FLOAT`: Initial delay between requests
- `--disable-adaptive-control`: Disable adaptive rate control
- `--aggressive-throttling`: Use more aggressive throttling

### Content Filtering Options

- `--include-headers`: Include header content
- `--include-menus`: Include menu/navigation content
- `--include-footers`: Include footer content
- `--include-sidebars`: Include sidebar content
- `--exclude-selectors TEXT`: Custom CSS selectors to exclude

### Domain Options

- `--allow-subdomains`: Allow crawling across subdomains
- `--allowed-extensions TEXT`: Additional file extensions to allow

### Special Modes

- `--spa`: Enable SPA mode for JavaScript-heavy sites
- `--markdown-mode`: Save content as markdown instead of keyword searching
- `--include-all-content`: Include all page content in markdown mode

### Configuration Options

- `--config FILE`: Load configuration from file
- `--save-config FILE`: Save configuration to file

## Examples

### Basic Keyword Search

```bash
spider https://example.com --keywords "product,service,feature"
```

### Advanced Keyword Search

```bash
spider https://docs.example.com --keywords "api,integration,tutorial" --path-prefix "/api/" --max-pages 100 --max-workers 6
```

### Markdown Extraction

```bash
spider https://blog.example.com --markdown-mode --include-headers --exclude-selectors ".comments,.author-bio"
```

### SPA Website

```bash
spider https://app.example.com --keywords "dashboard,settings,profile" --spa --min-delay 1.0 --aggressive-throttling
```

## Responsible Use

This crawler is designed to be respectful of target servers. Please use it responsibly:

- Don't overwhelm websites with too many requests
- Honor robots.txt directives
- Be mindful of rate limits and server load
- Don't use for scraping content that violates terms of service

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.