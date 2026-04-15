import importlib


def test_package_importable():
    mod = importlib.import_module("clawsocialarena")
    assert mod is not None


def test_package_has_version():
    import clawsocialarena
    assert hasattr(clawsocialarena, "__version__")
