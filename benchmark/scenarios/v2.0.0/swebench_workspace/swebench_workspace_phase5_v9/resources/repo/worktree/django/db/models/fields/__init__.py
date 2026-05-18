# Reduced source stub for django/db/models/fields/__init__.py.
# Reconstructed from the SWE-bench gold patch context.


def contribute_to_class(self, cls, name, private_only=False):
            if not getattr(cls, self.attname, None):
                setattr(cls, self.attname, self.descriptor_class(self))
        if self.choices is not None:
            setattr(cls, 'get_%s_display' % self.name,
                    partialmethod(cls._get_FIELD_display, field=self))

    def get_filter_kwargs_for_object(self, obj):
        """
