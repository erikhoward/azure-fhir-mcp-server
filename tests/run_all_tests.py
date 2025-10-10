#!/usr/bin/env python3
"""
Comprehensive Test Runner

Main test runner for all Azure FHIR MCP Server tests.
Run this to execute all test suites with coverage reporting.
"""

import subprocess
import sys
from pathlib import Path


def run_tests():
    """Run all test suites for the Azure FHIR MCP Server."""

    # Change to the project root directory
    project_root = Path(__file__).parent.parent

    print("="*60)
    print("AZURE FHIR MCP SERVER - COMPREHENSIVE TEST SUITE")
    print("="*60)
    print(f"Project root: {project_root}")
    print(f"Python version: {sys.version}")
    print("-"*60)

    # Test command with coverage
    test_cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",                     # Verbose output
        "--tb=short",            # Short traceback format
        "--strict-markers",      # Strict marker checking
        "--cov=src/azure_fhir_mcp_server",  # Coverage for source
        "--cov-report=term-missing",         # Show missing lines
        "--cov-report=html:htmlcov",         # HTML coverage report
        "--cov-fail-under=80",               # Require 80% coverage
        "-x",                                # Stop on first failure
    ]

    print("Running command:")
    print(" ".join(test_cmd))
    print("-"*60)

    # Run the tests
    try:
        result = subprocess.run(
            test_cmd,
            cwd=project_root,
            check=False,
            capture_output=False
        )

        print("-"*60)
        if result.returncode == 0:
            print("✅ ALL TESTS PASSED!")
            print("📊 Coverage report generated in htmlcov/index.html")
        else:
            print("❌ TESTS FAILED!")
            print(f"Exit code: {result.returncode}")
        print("="*60)

        return result.returncode

    except KeyboardInterrupt:
        print("\n❌ Tests interrupted by user")
        return 1
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        print(f"❌ Error running tests: {e}")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
