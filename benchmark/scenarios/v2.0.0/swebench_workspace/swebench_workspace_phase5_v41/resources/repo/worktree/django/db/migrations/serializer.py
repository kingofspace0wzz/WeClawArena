# Reduced source stub for django/db/migrations/serializer.py.
# Reconstructed from the SWE-bench gold patch context.


def serialize(self):
            if module == builtins.__name__:
                return self.value.__name__, set()
            else:
                return "%s.%s" % (module, self.value.__name__), {"import %s" % module}


class UUIDSerializer(BaseSerializer):
