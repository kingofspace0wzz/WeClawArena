import json
from pathlib import Path

from clawsocialarena.llm.costing import TokenUsage
from clawsocialarena.simulation.batch_runner import BatchUsage, build_batch_report
from scripts import generate_qc_report


def test_generate_qc_report_cli_writes_markdown_report(tmp_path: Path) -> None:
    batch_dir = tmp_path / "benchmark" / "batches" / "batch-qc-cli"
    batch_dir.mkdir(parents=True)
    report = build_batch_report(
        batch_id="batch-qc-cli",
        scenario_ids=["scenario-a"],
        accepted_scenario_ids=["scenario-a"],
        failed_scenarios=[],
        usage=BatchUsage(
            construction=TokenUsage(model="gpt-5"),
            simulation=TokenUsage(model="gpt-4.1-mini"),
        ),
        stop_for_review=True,
    )
    (batch_dir / "batch_report.json").write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    feedback_path = tmp_path / "review_feedback.json"
    feedback_path.write_text(
        json.dumps(
            {
                "evaluation_only_issues": ["Evaluator labels one refusal as attack uptake."],
                "recommended_decision": "re_score",
            }
        ),
        encoding="utf-8",
    )

    rc = generate_qc_report.main(
        [
            "--batch-dir",
            str(batch_dir),
            "--review-feedback",
            str(feedback_path),
        ]
    )

    output_path = tmp_path / "benchmark" / "reviews" / "batch-qc-cli-qc-report.md"
    assert rc == 0
    assert output_path.exists()
    markdown = output_path.read_text(encoding="utf-8")
    assert "# Construction QC Report: batch-qc-cli" in markdown
    assert "- Decision: re_score" in markdown
    assert "- Evaluator labels one refusal as attack uptake." in markdown
