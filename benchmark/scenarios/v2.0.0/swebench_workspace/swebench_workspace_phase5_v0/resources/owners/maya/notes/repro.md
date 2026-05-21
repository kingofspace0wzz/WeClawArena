# Reproduction Notes

Instance: astropy__astropy-12907
Repo: astropy/astropy
Issue digest: Fix modeling.separability_matrix so nested CompoundModels preserve the right-hand separability block instead of replacing it with ones.
Required file evidence: astropy/modeling/separable.py
Target tests to record before review: astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6], astropy/modeling/tests/test_separable.py::test_separable[compound_model9-result9]
Use these notes as the source of truth for the target tests and issue symptom before asking for review.
