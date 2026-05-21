# Reproduction Notes

Instance: sympy__sympy-15345
Repo: sympy/sympy
Issue digest: mathematica_code gives wrong output with Max
If I run the code

```
x = symbols('x')
mathematica_code(Max(x,2))
```

then I would expect the output `'Max[x,2]'` which is valid Mathematica code but instead I get `'Max(2, x)'` which is not valid Mathematica code.

Required file evidence: sympy/printing/mathematica.py
Target tests to record before review: test_Function
Use these notes as the source of truth for the target tests and issue symptom before asking for review.
