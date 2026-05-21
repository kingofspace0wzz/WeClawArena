# Risk Notes

Problem behavior to preserve outside the fix: Fix coth(log(tan(x))).subs(...) for integral values by using the computed coth value instead of an undefined variable.
Review risk marker: SYMPY-SYMPY-13480-REVIEW-RISK.
Do not approve unrelated cleanup just because the diff is small.
