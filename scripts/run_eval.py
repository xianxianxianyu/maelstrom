#!/usr/bin/env python
"""CLI entry point for running eval cases.

Usage:
    python scripts/run_eval.py [--engine gap|synthesis|planning|experiment]
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.eval.framework import EvalRunner, load_case_from_file


async def main():
    parser = argparse.ArgumentParser(description="Run Maelstrom eval suite")
    parser.add_argument("--engine", type=str, default=None, help="Filter by engine (gap, synthesis, planning, experiment)")
    parser.add_argument("--case", type=str, default=None, help="Run a specific case file")
    args = parser.parse_args()

    cases_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "eval", "cases")
    cases_dir = os.path.abspath(cases_dir)

    if args.case:
        files = [args.case]
    else:
        files = sorted(glob.glob(os.path.join(cases_dir, "*.json")))

    cases = []
    for f in files:
        case = load_case_from_file(f)
        if args.engine and case.engine != args.engine:
            continue
        cases.append(case)

    if not cases:
        print("No eval cases found.")
        return

    print(f"Running {len(cases)} eval case(s)...\n")
    runner = EvalRunner()
    suite_result = await runner.run_suite(cases)

    for r in suite_result.results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.case_id}")
        if r.error:
            print(f"         Error: {r.error}")
        if not r.schema_valid:
            print(f"         Schema validation failed")
        for check, ok in r.quality_checks.items():
            if not ok:
                print(f"         Quality check failed: {check}")

    print(f"\nTotal: {suite_result.total}  Passed: {suite_result.passed}  Failed: {suite_result.failed}")


if __name__ == "__main__":
    asyncio.run(main())
