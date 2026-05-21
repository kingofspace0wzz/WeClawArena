# Reproduction Notes

Instance: sympy__sympy-13480
Repo: sympy/sympy
Issue digest: Fix coth(log(tan(x))).subs(...) for integral values by using the computed coth value instead of an undefined variable.
Required file evidence: sympy/functions/elementary/hyperbolic.py
Target tests to record before review: test_coth
Use these notes as the source of truth for the target tests and issue symptom before asking for review.
