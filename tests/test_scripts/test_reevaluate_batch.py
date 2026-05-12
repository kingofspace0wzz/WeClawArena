import json

from scripts import reevaluate_batch


def test_reevaluate_batch_cli_writes_report(monkeypatch, tmp_path) -> None:
    batch_dir = tmp_path / "batch-0001"
    report_path = tmp_path / "reevaluated_report.json"
    calls = []

    class FakeReport:
        accepted_count = 3
        failed_count = 0

        def model_dump(self, mode="python"):
            calls.append(mode)
            return {
                "batch_id": "batch-0001",
                "accepted_count": self.accepted_count,
                "failed_count": self.failed_count,
            }

    def fake_reevaluate_existing_batch(**kwargs):
        assert kwargs["batch_dir"] == batch_dir
        assert kwargs["recompute_scorecards"] is True
        return FakeReport()

    monkeypatch.setattr(
        reevaluate_batch,
        "reevaluate_existing_batch",
        fake_reevaluate_existing_batch,
    )

    rc = reevaluate_batch.main(
        [
            "--batch-dir",
            str(batch_dir),
            "--recompute-scorecards",
            "--out",
            str(report_path),
        ]
    )

    assert rc == 0
    assert calls == ["json"]
    assert json.loads(report_path.read_text()) == {
        "batch_id": "batch-0001",
        "accepted_count": 3,
        "failed_count": 0,
    }

