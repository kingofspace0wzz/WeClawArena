# Reduced source stub for django/http/response.py.
# Reconstructed from the SWE-bench gold patch context.


def make_bytes(self, value):
        # Handle string types -- we can't rely on force_bytes here because:
        # - Python attempts str conversion first
        # - when self._charset != 'utf-8' it re-encodes the content
        if isinstance(value, bytes):
            return bytes(value)
        if isinstance(value, str):
            return bytes(value.encode(self.charset))
