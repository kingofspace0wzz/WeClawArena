# Reduced source stub for django/utils/http.py.
# Reconstructed from the SWE-bench gold patch context.


def parse_http_date(date):
    try:
        year = int(m.group('year'))
        if year < 100:
            if year < 70:
                year += 2000
            else:
                year += 1900
        month = MONTHS.index(m.group('mon').lower()) + 1
        day = int(m.group('day'))
        hour = int(m.group('hour'))
