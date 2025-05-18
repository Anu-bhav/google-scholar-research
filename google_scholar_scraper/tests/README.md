# Google Scholar Research Tool Tests

This directory contains the test suite for the Google Scholar Research Tool.

## Directory Structure

- `conftest.py`: Contains pytest fixtures and configurations
- `data/`: Sample data files for testing (HTML samples, JSON responses, etc.)
- `test_*.py`: Test files for each module

## Running Tests

To run all tests:

```bash
# Run all tests
python -m pytest

# Run specific test modules
python -m pytest test_query_builder.py
python -m pytest test_parser.py
python -m pytest test_proxy_manager.py
```

Alternatively, you can use the run_tests.py script:

```bash
# Run all tests
python run_tests.py

# Run specific test modules
python run_tests.py query_builder
python run_tests.py parser proxy
```
