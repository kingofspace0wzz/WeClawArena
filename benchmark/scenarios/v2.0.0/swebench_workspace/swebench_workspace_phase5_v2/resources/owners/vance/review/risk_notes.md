# Risk Notes

Problem behavior to preserve outside the fix: Fix DataArray.to_unstacked_dataset for single-dimension variables so stacked arrays can roundtrip without MergeError.
Review risk marker: PYDATA-XARRAY-4094-REVIEW-RISK.
Do not approve unrelated cleanup just because the diff is small.
