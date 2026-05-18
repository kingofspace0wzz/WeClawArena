# Reduced source stub for sphinx/ext/viewcode.py.
# Reconstructed from the SWE-bench gold patch context.


def collect_pages(app: Sphinx) -> Generator[Tuple[str, Dict[str, Any], str], Non
    env = app.builder.env
    if not hasattr(env, '_viewcode_modules'):
        return
    highlighter = app.builder.highlighter  # type: ignore
    urito = app.builder.get_relative_uri
