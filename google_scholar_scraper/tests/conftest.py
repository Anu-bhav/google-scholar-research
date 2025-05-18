"""
Test configuration for Google Scholar Scraper tests.
Contains fixtures and configuration for pytest.
"""
import os
import sys
import pytest
from pathlib import Path

# Add the parent directory to sys.path to allow imports from the main package
# Since the package structure is google_scholar_scraper/google_scholar_scraper
# we need to make sure both are in the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Create directories for test data if they don't exist
os.makedirs(os.path.join(os.path.dirname(__file__), 'data'), exist_ok=True)

# Common fixtures for tests
@pytest.fixture
def sample_html_path():
    """Path to sample HTML files directory"""
    return os.path.join(os.path.dirname(__file__), 'data')

@pytest.fixture
def sample_search_result_html():
    """Sample Google Scholar search result HTML"""
    html_path = os.path.join(os.path.dirname(__file__), 'data', 'sample_search_result.html')
    if os.path.exists(html_path):
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""
