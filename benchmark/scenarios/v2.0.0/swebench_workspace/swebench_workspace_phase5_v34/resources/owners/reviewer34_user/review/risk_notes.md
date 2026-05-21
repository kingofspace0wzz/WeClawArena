# Risk Notes

Problem behavior to preserve outside the fix: mathematica_code gives wrong output with Max
If I run the code

```
x = symbols('x')
mathematica_code(Max(x,2))
```

then I would expect the output `'Max[x,2]'` which is valid Mathematica code but instead I get `'Max(2, x)'` which is not valid Mathematica code.

Review risk marker: SYMPY-SYMPY-15345-REVIEW-RISK.
Do not approve unrelated cleanup just because the diff is small.
