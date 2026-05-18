import os

def _is_ignored_file(element, ignore_list, ignore_list_re, ignore_list_paths_re):
    basename = os.path.basename(element)
    return basename in ignore_list
