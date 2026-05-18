# Reduced source stub for django/db/models/sql/query.py.
# Reconstructed from the SWE-bench gold patch context.


def check_related_objects(self, field, value, opts):

    """
    def check_filterable(self, expression):
        """Raise an error if expression cannot be used in a WHERE clause."""
        if not getattr(expression, 'filterable', True):
            raise NotSupportedError(
                expression.__class__.__name__ + ' is disallowed in the filter '
                'clause.'
