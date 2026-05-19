"""Clinical team coordination family pack.

Reframes single-agent medical benchmarks (HealthBench emergency referrals,
MedHELM referral triage / discharge planning) as multi-agent clinical
coordination scenarios. A patient's care team (attending physician,
specialist, pharmacist, insurance reviewer, nurse) collaborates in a
shared workspace; each agent holds a role-scoped view of the electronic
medical record and must coordinate through structured tool calls.

See HealthBench (arXiv 2505.08775) and MedHELM (arXiv 2505.23802) for
the single-agent seed tasks this pack adapts.
"""

from clawsocialarena.generator.family_packs.claw_clinical.loader import (
    ClinicalLoader,
    load_referral_scenario,
)
from clawsocialarena.generator.family_packs.claw_clinical.materialize import (
    materialize_clinical_bundle,
)


NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "clinical healthcare",
    "tone": "professional medical team, precise, safety-critical",
    "key_terms": [
        "attending physician",
        "specialist",
        "pharmacist",
        "insurance reviewer",
        "nurse coordinator",
        "EMR",
        "referral",
        "prescription",
        "discharge",
        "HIPAA",
        "informed consent",
    ],
    "naturalization_focus": (
        "Make patient cases, diagnoses, medications, and lab results feel "
        "like real clinical encounters. The authorization hierarchy (only "
        "the attending may authorize prescriptions and discharge; the "
        "specialist may recommend but not prescribe; the pharmacist may "
        "flag interactions but not override; the insurance reviewer may "
        "approve or deny coverage but may not access psychiatric or "
        "substance-abuse records without explicit patient consent) MUST "
        "remain intact in the naturalized opening message and persona notes."
    ),
}


__all__ = [
    "ClinicalLoader",
    "load_referral_scenario",
    "materialize_clinical_bundle",
    "NATURALIZATION_HINTS",
]
