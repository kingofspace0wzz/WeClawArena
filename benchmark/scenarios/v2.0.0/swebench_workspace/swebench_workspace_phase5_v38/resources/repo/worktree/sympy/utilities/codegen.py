# Reduced source stub for sympy/utilities/codegen.py.
# Reconstructed from the SWE-bench gold patch context.


def routine(self, name, expr, argument_sequence=None, global_vars=None):
        arg_list = []

        # setup input argument list
        array_symbols = {}
        for array in expressions.atoms(Indexed) | local_expressions.atoms(Indexed):
            array_symbols[array.base.label] = array

def routine(self, name, expr, argument_sequence=None, global_vars=None):

        for symbol in sorted(symbols, key=str):
            if symbol in array_symbols:
                dims = []
                array = array_symbols[symbol]
                for dim in array.shape:
                    dims.append((S.Zero, dim - 1))
                metadata = {'dimensions': dims}
            else:
                metadata = {}


def routine(self, name, expr, argument_sequence=None, global_vars=None):
                try:
                    new_args.append(name_arg_dict[symbol])
                except KeyError:
                    new_args.append(InputArgument(symbol))
            arg_list = new_args

        return Routine(name, arg_list, return_val, local_vars, global_vars)
