# Reduced source stub for django/forms/models.py.
# Reconstructed from the SWE-bench gold patch context.


def to_python(self, value):
                value = getattr(value, key)
            value = self.queryset.get(**{key: value})
        except (ValueError, TypeError, self.queryset.model.DoesNotExist):
            raise ValidationError(self.error_messages['invalid_choice'], code='invalid_choice')
        return value

    def validate(self, value):
