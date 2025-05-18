#!/usr/bin/env python
"""
Test runner for Google Scholar Scraper project.
Run this script to execute all tests or specific test modules.

Usage:
    python run_tests.py                  # Run all tests
    python run_tests.py query_builder    # Run only QueryBuilder tests
    python run_tests.py parser proxy     # Run Parser and ProxyManager tests
"""

import sys
import unittest

import pytest


def run_tests_with_unittest(test_names=None):
    """Run tests using unittest framework"""
    if test_names:
        test_suite = unittest.TestSuite()
        test_loader = unittest.TestLoader()

        for test_name in test_names:
            if test_name.lower() == "query_builder":
                from tests import test_query_builder

                test_suite.addTest(test_loader.loadTestsFromModule(test_query_builder))
            elif test_name.lower() == "parser":
                from tests import test_parser

                test_suite.addTest(test_loader.loadTestsFromModule(test_parser))
            elif test_name.lower() == "proxy" or test_name.lower() == "proxy_manager":
                from tests import test_proxy_manager

                test_suite.addTest(test_loader.loadTestsFromModule(test_proxy_manager))
            elif test_name.lower() == "author" or test_name.lower() == "author_profile_parser":
                from tests import test_author_profile_parser

                test_suite.addTest(test_loader.loadTestsFromModule(test_author_profile_parser))
            elif test_name.lower() == "utils" or test_name.lower() == "utility":
                from tests import test_utils

                test_suite.addTest(test_loader.loadTestsFromModule(test_utils))
            # Add more modules as needed
    else:
        # Run all tests
        test_suite = unittest.defaultTestLoader.discover("tests")

    test_runner = unittest.TextTestRunner(verbosity=2)
    return test_runner.run(test_suite)


def run_tests_with_pytest(test_names=None):
    """Run tests using pytest framework"""
    pytest_args = ["-v", "google_scholar_scraper/tests/"]

    if test_names:
        pytest_args = ["-v"]
        for test_name in test_names:
            if test_name.lower() == "query_builder":
                pytest_args.append("google_scholar_scraper/tests/test_query_builder.py")
            elif test_name.lower() == "parser":
                pytest_args.append("google_scholar_scraper/tests/test_parser.py")
            elif test_name.lower() == "proxy" or test_name.lower() == "proxy_manager":
                pytest_args.append("google_scholar_scraper/tests/test_proxy_manager.py")
            elif test_name.lower() == "author" or test_name.lower() == "author_profile_parser":
                pytest_args.append("google_scholar_scraper/tests/test_author_profile_parser.py")
            elif test_name.lower() == "utils" or test_name.lower() == "utility":
                pytest_args.append("google_scholar_scraper/tests/test_utils.py")
            # Add more modules as needed

    return pytest.main(pytest_args)


if __name__ == "__main__":
    # Get test names from command-line arguments
    test_names = sys.argv[1:] if len(sys.argv) > 1 else None

    # Use pytest for running tests
    result = run_tests_with_pytest(test_names)

    # Exit with appropriate exit code
    sys.exit(0 if result == 0 else 1)
