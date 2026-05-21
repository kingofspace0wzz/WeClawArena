# Reproduction Notes

Instance: sphinx-doc__sphinx-8721
Repo: sphinx-doc/sphinx
Issue digest: viewcode creates pages for epub even if `viewcode_enable_epub=False` on `make html epub`
**Describe the bug**
viewcode creates pages for epub even if `viewcode_enable_epub=False` on `make html epub`

**To Reproduce**
```
$ make html epub
```

**Expected behavior**
module pages should not be created for epub by default.

**Your project**
No

**Screenshots**
No

**Environment info**
- OS: Mac
- Python version: 3.9.1
- Sphinx version: HEAD of 3.x
- Sphinx extensions:  sphinx.ext.viewcode
- Extra tools: No

**Additional context**
No


Required file evidence: sphinx/ext/viewcode.py
Target tests to record before review: tests/test_ext_viewcode.py::test_viewcode_epub_default
Use these notes as the source of truth for the target tests and issue symptom before asking for review.
