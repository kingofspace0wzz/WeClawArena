# Reproduction Notes

Instance: pytest-dev__pytest-7432
Repo: pytest-dev/pytest
Issue digest: Fix pytest --runxfail skip reporting so skip locations still point at the skipped item.
Required file evidence: src/_pytest/skipping.py
Target tests to record before review: testing/test_skipping.py::TestXFail::test_xfail_run_with_skip_mark[test_input1-expected1]
Use these notes as the source of truth for the target tests and issue symptom before asking for review.
