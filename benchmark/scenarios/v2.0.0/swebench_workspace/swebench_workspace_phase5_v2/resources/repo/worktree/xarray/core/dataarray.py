class DataArray:
    def to_unstacked_dataset(self, dim, level=0):
        data_dict = {}
        for k in variables:
            data_dict[k] = self.sel({variable_dim: k}).squeeze(drop=True)
        return Dataset(data_dict)
