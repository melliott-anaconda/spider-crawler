@echo off
"%PREFIX%\python.exe" -m pip install selenium-stealth>=1.0.6 undetected-chromedriver>=3.4.6 playwright>=1.51.0
"%PREFIX%\python.exe" -m playwright install
