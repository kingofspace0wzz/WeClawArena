def pytest_runtest_makereport(item, call):
    if item._store.get('xfailed', False):
        pass
    elif item._store.get('skipped_by_mark', True):
        pass
