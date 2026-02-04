---
name: "web-scraper"
description: "Fetches and extracts main content from web pages using Trafilatura. Invoke when user needs to read full article content or scrape data from URLs."
---

# Web Scraper

This skill uses `trafilatura` to robustly extract text from web pages, ignoring boilerplate, ads, and navigation.

## Usage

1. Use `execute_script` to run `python scripts/scrape.py <url>`.
2. The script returns the extracted title and main text as JSON.

## Dependencies

- trafilatura (pip install trafilatura)
