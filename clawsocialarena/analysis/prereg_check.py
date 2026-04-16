"""Pre-registration reconciler — compares reported results against preregistration.

For each hypothesis H1-H5 (spec §5.7), emit a verdict: ``supported``,
``not_supported``, or ``inconclusive``. Produces a markdown report.

Current coverage:
    H2 — Enforce < Passive < Baseline on privacy leak + security ASR.
    H4 — Vanilla-AA overestimates auditability vs SAF.

H1, H3, H5 are left for the batch runner (Phase 6.1) to surface the
required cross-family diagnostics.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from clawsocialarena.analysis.stats import paired_wilcoxon


def h2_verdict(df: pd.DataFrame) -> dict:
    """H2: Enforce reduces privacy leak + security ASR vs Baseline.

    Pragmatic check: paired Wilcoxon on each family (baseline vs enforce);
    supported if p < 0.05 on both *and* the median effect points the right
    way (enforce lower than baseline).
    """
    priv = paired_wilcoxon(
        df,
        metric_family="privacy",
        metric_name="leak_rate",
        cond_a="baseline",
        cond_b="enforce",
    )
    sec = paired_wilcoxon(
        df,
        metric_family="security",
        metric_name="asr",
        cond_a="baseline",
        cond_b="enforce",
    )

    def _median_drops(family: str, name: str) -> bool:
        sub = df[(df["metric_family"] == family) & (df["metric_name"] == name)]
        m_base = sub[sub["condition"] == "baseline"]["value"].median()
        m_enf = sub[sub["condition"] == "enforce"]["value"].median()
        if pd.isna(m_base) or pd.isna(m_enf):
            return False
        return m_enf < m_base

    have_p = not (pd.isna(priv["p_value"]) or pd.isna(sec["p_value"]))
    verdict: str
    if not have_p:
        verdict = "inconclusive"
    else:
        sig = priv["p_value"] < 0.05 and sec["p_value"] < 0.05
        directional = _median_drops("privacy", "leak_rate") and _median_drops(
            "security", "asr"
        )
        verdict = "supported" if (sig and directional) else "not_supported"

    return {
        "hypothesis": "H2",
        "privacy_test": priv,
        "security_test": sec,
        "verdict": verdict,
    }


def h4_verdict(df: pd.DataFrame) -> dict:
    """H4: Vanilla-AA overestimates auditability vs SAF.

    Requires both ``saf:overall`` and ``saf:vanilla_aa_overall`` per-scenario
    metrics in df. Supported if vanilla > SAF on >= 75% of paired scenarios.
    """
    saf = df[(df["metric_family"] == "saf") & (df["metric_name"] == "overall")]
    vaa = df[
        (df["metric_family"] == "saf") & (df["metric_name"] == "vanilla_aa_overall")
    ]
    paired = pd.concat(
        [
            saf.groupby("scenario_id")["value"].mean().rename("saf"),
            vaa.groupby("scenario_id")["value"].mean().rename("vaa"),
        ],
        axis=1,
    ).dropna()
    if len(paired) == 0:
        return {"hypothesis": "H4", "n": 0, "verdict": "inconclusive"}
    frac_over = float((paired["vaa"] > paired["saf"]).mean())
    verdict = "supported" if frac_over >= 0.75 else "not_supported"
    return {
        "hypothesis": "H4",
        "n": int(len(paired)),
        "frac_vaa_over_saf": frac_over,
        "verdict": verdict,
    }


def reconcile(csv_path: Path) -> list[dict]:
    """Run all hypothesis checks against the aggregated long-format CSV."""
    df = pd.read_csv(csv_path)
    return [h2_verdict(df), h4_verdict(df)]


def render_report(results: list[dict]) -> str:
    """Render a list of hypothesis verdicts as a markdown report."""
    lines = ["# Pre-registration reconciliation", ""]
    for r in results:
        lines.append(f"## {r['hypothesis']}")
        lines.append(f"- Verdict: **{r['verdict']}**")
        for k, v in r.items():
            if k in ("hypothesis", "verdict"):
                continue
            lines.append(f"- {k}: {v}")
        lines.append("")
    return "\n".join(lines)
