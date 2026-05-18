# Reduced source stub for django/db/models/enums.py.
# Reconstructed from the SWE-bench gold patch context.


def values(cls):

class Choices(enum.Enum, metaclass=ChoicesMeta):
    """Class for creating enumerated choices."""
    pass


class IntegerChoices(int, Choices):
