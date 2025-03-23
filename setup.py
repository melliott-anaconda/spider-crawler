from setuptools import setup, find_packages

setup(
    name="spider-crawler",
    version="1.0.0",
    description="A flexible web crawler for keyword searching and content extraction",
    author="Michael Elliott",
    author_email="melliott@anaconda.com",
    url="https://github.com/melliott-anaconda/spider-crawler",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "selenium>=4.1.0",
        "beautifulsoup4>=4.10.0",
        "html2text>=2020.1.16",
        "webdriver-manager>=3.5.2",
        "selenium-stealth>=1.0.6",  
        "undetected-chromedriver>=3.4.6", 
    ],
    entry_points={
        'console_scripts': [
            'spider=spider.__main__:main',
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)