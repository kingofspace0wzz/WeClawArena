from pathlib import Path


def test_bundle_relative_path_drops_source_prefixes() -> None:
    from clawsocialarena.generator.phase5_store_layout import (
        bundle_relative_path_for_base,
    )

    assert bundle_relative_path_for_base("CD-A-marble_research__t0") == Path(
        "research/CD-A-marble_research__t0"
    )
    assert bundle_relative_path_for_base("CM-A-marble_bargaining__t0") == Path(
        "bargaining/CM-A-marble_bargaining__t0"
    )
    assert bundle_relative_path_for_base("CM-C-marble_bidding__t0") == Path(
        "bidding/CM-C-marble_bidding__t0"
    )


def test_resolve_store_base_dir_accepts_manifest_path_and_flat_fallback(
    tmp_path: Path,
) -> None:
    from clawsocialarena.generator.phase5_store_layout import resolve_store_base_dir

    store = tmp_path / "store"
    nested = store / "research" / "CD-A-marble_research__t0"
    flat = store / "CD-A-marble_research__t1"
    nested.mkdir(parents=True)
    flat.mkdir(parents=True)

    assert resolve_store_base_dir(
        store_dir=store,
        base_id="CD-A-marble_research__t0",
        bundle_dir="research/CD-A-marble_research__t0",
    ) == nested
    assert resolve_store_base_dir(
        store_dir=store,
        base_id="CD-A-marble_research__t1",
    ) == flat
