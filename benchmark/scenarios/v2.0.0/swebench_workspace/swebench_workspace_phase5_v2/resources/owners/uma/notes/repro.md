# Reproduction Notes

Instance: pydata__xarray-4094
Repo: pydata/xarray
Issue digest: Fix DataArray.to_unstacked_dataset for single-dimension variables so stacked arrays can roundtrip without MergeError.
Required file evidence: xarray/core/dataarray.py
Target tests to record before review: xarray/tests/test_dataset.py::TestDataset::test_to_stacked_array_to_unstacked_dataset
Use these notes as the source of truth for the target tests and issue symptom before asking for review.
