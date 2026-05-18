# Reduced source stub for django/contrib/admin/utils.py.
# Reconstructed from the SWE-bench gold patch context.


def display_for_field(value, field, empty_value_display):
        return formats.number_format(value)
    elif isinstance(field, models.FileField) and value:
        return format_html('<a href="{}">{}</a>', value.url, value)
    else:
        return display_for_value(value, empty_value_display)
