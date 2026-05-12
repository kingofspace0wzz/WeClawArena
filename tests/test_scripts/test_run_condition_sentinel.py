from pathlib import Path

from clawsocialarena.llm.costing import TokenUsage
from clawsocialarena.simulation.batch_runner import BatchUsage, build_batch_report
from scripts import run_condition_sentinel


def test_condition_sentinel_cli_writes_report_with_requested_conditions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(run_condition_sentinel, "require_openai_key", lambda: None)
    monkeypatch.setattr(run_condition_sentinel, "docker_available", lambda: True)

    def fake_run_condition_sentinel_batch(**kwargs):
        assert kwargs["source_batch_dir"] == tmp_path / "source"
        assert kwargs["batch_id"] == "sentinel-0001"
        assert kwargs["conditions"] == ["baseline", "enforce"]
        assert kwargs["scenario_ids"] == ["scenario-a"]
        return build_batch_report(
            batch_id="sentinel-0001",
            scenario_ids=["scenario-a--baseline", "scenario-a--enforce"],
            accepted_scenario_ids=["scenario-a--baseline", "scenario-a--enforce"],
            failed_scenarios=[],
            usage=BatchUsage(
                construction=TokenUsage(model="gpt-5.2"),
                simulation=TokenUsage(model="gpt-4.1-mini"),
            ),
            stop_for_review=True,
            condition="mixed",
        )

    monkeypatch.setattr(
        run_condition_sentinel,
        "run_condition_sentinel_batch",
        fake_run_condition_sentinel_batch,
    )

    rc = run_condition_sentinel.main(
        [
            "--source-batch-dir",
            str(tmp_path / "source"),
            "--batch-id",
            "sentinel-0001",
            "--out",
            str(tmp_path / "batches"),
            "--scenario-id",
            "scenario-a",
            "--condition",
            "baseline",
            "--condition",
            "enforce",
        ]
    )

    assert rc == 0
    assert (tmp_path / "batches" / "sentinel-0001" / "batch_report.json").exists()
