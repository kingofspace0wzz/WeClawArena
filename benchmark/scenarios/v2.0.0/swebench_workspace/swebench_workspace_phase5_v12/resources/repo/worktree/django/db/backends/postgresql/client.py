# Reduced source stub for django/db/backends/postgresql/client.py.
# Reconstructed from the SWE-bench gold patch context.


def settings_to_cmd_args_env(cls, settings_dict, parameters):
            args += ["-h", host]
        if port:
            args += ["-p", str(port)]
        if dbname:
            args += [dbname]
        args.extend(parameters)

        env = {}
        if passwd:
