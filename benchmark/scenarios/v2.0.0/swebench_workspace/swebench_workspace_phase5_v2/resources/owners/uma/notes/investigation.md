# Investigation Notes

Problem: Fix DataArray.to_unstacked_dataset for single-dimension variables so stacked arrays can roundtrip without MergeError.
Required files: xarray/core/dataarray.py
