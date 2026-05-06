import json

import pytest

from clawsocialarena.generator.profiles import ProfileBank, ProfileBankEmpty


def _write_profile(path, *, profile_id: str, name: str, occupation: str) -> None:
    payload = {
        "profile_id": profile_id,
        "name": name,
        "demographics": {"occupation": occupation},
        "health": {
            "conditions": ["synthetic asthma"],
            "medications": ["synthetic inhaler"],
        },
        "finance": {"debts": ["synthetic student loan"]},
        "social": {
            "relationships": [
                "Advisor: Morgan Lee (academic planning)",
            ],
            "close_contacts": [{"name": "Riley Chen", "relationship": "roommate"}],
        },
        "professional": {"field": "public health", "role": "research assistant"},
        "shared_contexts": ["visa-appointment"],
        "trust_levels": {"profile_bob": 0.9},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_profile_bank_loads_agentsocialbench_profile_metadata(tmp_path) -> None:
    _write_profile(
        tmp_path / "profile_alex.json",
        profile_id="profile_alex",
        name="Alex Rivera",
        occupation="Graduate Student",
    )

    bank = ProfileBank.from_dir(tmp_path, dataset_version="asb-v1")
    profile = bank.get("profile_alex")

    assert profile.name == "Alex Rivera"
    assert profile.dataset == "AgentSocialBench"
    assert profile.dataset_version == "asb-v1"
    assert profile.profile_ref == "asb://profiles/profile_alex"
    assert profile.profile_hash.startswith("sha256:")
    assert profile.source_path is not None
    assert profile.source_path.name == "profile_alex.json"
    assert profile.privacy_boundary_refs == (
        "asb://profiles/profile_alex#sensitive_items/0",
        "asb://profiles/profile_alex#sensitive_items/1",
        "asb://profiles/profile_alex#sensitive_items/2",
    )
    assert "graduate student" in profile.domain
    assert "synthetic asthma" in profile.sensitive_items
    assert profile.relationships["Morgan Lee"] == "Advisor"


def test_profile_bank_uses_existing_profile_ref_when_present(tmp_path) -> None:
    payload = {
        "profile_id": "profile_custom",
        "profile_ref": "asb://profiles/custom/profile_custom",
        "name": "Custom User",
        "sensitive_items": ["synthetic account number"],
    }
    (tmp_path / "custom.json").write_text(json.dumps(payload), encoding="utf-8")

    profile = ProfileBank.from_dir(tmp_path, dataset_version="asb-v1").get(
        "profile_custom"
    )

    assert profile.profile_ref == "asb://profiles/custom/profile_custom"
    assert profile.privacy_boundary_refs == (
        "asb://profiles/custom/profile_custom#sensitive_items/0",
    )


def test_profile_bank_sampling_is_seeded_and_category_aware(tmp_path) -> None:
    _write_profile(
        tmp_path / "profile_alex.json",
        profile_id="profile_alex",
        name="Alex Rivera",
        occupation="Graduate Student",
    )
    _write_profile(
        tmp_path / "profile_blair.json",
        profile_id="profile_blair",
        name="Blair Park",
        occupation="Clinic Coordinator",
    )

    bank = ProfileBank.from_dir(tmp_path, dataset_version="asb-v1")
    first = bank.sample_pair(seed=7, category="CU")
    second = bank.sample_pair(seed=7, category="CU")

    assert [profile.profile_id for profile in first] == [
        profile.profile_id for profile in second
    ]
    assert first[0].profile_id != first[1].profile_id


def test_profile_bank_missing_dir_raises_clear_error(tmp_path) -> None:
    with pytest.raises(ProfileBankEmpty, match="does not exist"):
        ProfileBank.from_dir(tmp_path / "missing", dataset_version="asb-v1")
