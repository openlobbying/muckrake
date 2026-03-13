"""
UK Electoral Commission political donations and loans crawler.

This module serves as the entry point for crawling both donations
and loans data from the Electoral Commission.
"""
from .donations import crawl_donations
from .loans import crawl_loans

# TODO: Probably worth splitting into two datasets

def crawl(dataset):
    """Main crawler entry point - crawls both donations and loans."""
    crawl_donations(dataset)
    crawl_loans(dataset)
    # crawl_spending(dataset)