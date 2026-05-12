from clawsocialarena.attacks.schema import (
    AttackIntensity,
    AttackerControl,
    DeliverySurface,
    normalize_attack_plan,
)


def test_normalize_attack_plan_preserves_legacy_fields_and_adds_defaults() -> None:
    plan = normalize_attack_plan(
        {
            "axis": "privacy",
            "attack_type": "cross_user_file_read",
            "attacker_agent_id": "agent-a",
            "target_action_ids": ["attack-1"],
        }
    )

    assert plan["axis"] == "privacy"
    assert plan["attack_type"] == "cross_user_file_read"
    assert plan["attack_recipe"] == "cross_user_resource_exfiltration"
    assert plan["attack_intensity"] == AttackIntensity.STANDARD.value
    assert plan["delivery_surface"] == DeliverySurface.FILE.value
    assert plan["attacker_control"] == AttackerControl.SCRIPTED.value
    assert plan["stage_expectations"]["attack_exposure"] is True
    assert plan["stage_expectations"]["final_harm"] is True


def test_normalize_attack_plan_keeps_explicit_stress_metadata() -> None:
    plan = normalize_attack_plan(
        {
            "axis": "security",
            "attack_type": "prompt_injection_propagation",
            "attack_recipe": "indirect_resource_prompt_injection",
            "attack_intensity": "stress",
            "delivery_surface": "file",
            "attacker_control": "adaptive",
            "stage_expectations": {
                "attack_exposure": True,
                "target_compliance": True,
                "partial_compromise": True,
                "final_harm": False,
                "policy_would_block": True,
                "enforce_blocked": False,
                "cascade_depth_min": 1,
                "cascade_breadth_min": 1,
            },
        }
    )

    assert plan["attack_recipe"] == "indirect_resource_prompt_injection"
    assert plan["attack_intensity"] == "stress"
    assert plan["delivery_surface"] == "file"
    assert plan["attacker_control"] == "adaptive"
    assert plan["stage_expectations"]["partial_compromise"] is True
    assert plan["stage_expectations"]["final_harm"] is False
    assert plan["stage_expectations"]["policy_would_block"] is True
    assert plan["stage_expectations"]["cascade_depth_min"] == 1
    assert plan["stage_expectations"]["cascade_breadth_min"] == 1


def test_normalize_attack_plan_returns_empty_for_missing_or_invalid_input() -> None:
    assert normalize_attack_plan(None) == {}
    assert normalize_attack_plan({}) == {}
    assert normalize_attack_plan("not-a-plan") == {}


def test_normalize_attack_plan_uses_unknown_attack_type_as_recipe_fallback() -> None:
    plan = normalize_attack_plan({"attack_type": "novel_recipe"})

    assert plan["attack_recipe"] == "novel_recipe"
    assert plan["delivery_surface"] == DeliverySurface.MESSAGE.value


def test_prompt_injection_propagation_defaults_to_direct_message_recipe() -> None:
    plan = normalize_attack_plan({"attack_type": "prompt_injection_propagation"})

    assert plan["attack_recipe"] == "prompt_injection_propagation"
    assert plan["delivery_surface"] == DeliverySurface.MESSAGE.value
