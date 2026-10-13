#!/usr/bin/python3
"""Retain an actual offline unittest transcript and machine-readable result."""
import io
import unittest
from pathlib import Path
from common import OUT,write_json


def main():
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_screen.py')
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (OUT/'audit/offline_tests.log').write_text(stream.getvalue())
    write_json('audit/test_results.json',{'tests_run':result.testsRun,'failures':len(result.failures),
        'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful(),
        'test_type':'offline contract regression with real decision bundles; mutations are unit fixtures, not scientific samples',
        'unimplemented_physical_test':'no real collision/reachability qualification because pre-decision occupancy is absent'})
    print(stream.getvalue())
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
