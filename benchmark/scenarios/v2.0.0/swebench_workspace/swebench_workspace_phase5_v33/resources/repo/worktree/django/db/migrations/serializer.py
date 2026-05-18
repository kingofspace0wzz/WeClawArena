# Reduced source stub for django/db/migrations/serializer.py.
# Reconstructed from the SWE-bench gold patch context.


class EnumSerializer(BaseSerializer):
    def serialize(self):
        enum_class = self.value.__class__
        module = enum_class.__module__
        v_string, v_imports = serializer_factory(self.value.value).serialize()
        imports = {'import %s' % module, *v_imports}
        return "%s.%s(%s)" % (module, enum_class.__name__, v_string), imports


class FloatSerializer(BaseSimpleSerializer):
