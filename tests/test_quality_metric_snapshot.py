from __future__ import annotations

from pathlib import Path

from scripts.quality.metric_snapshot import collect_metrics


def test_collect_metrics_counts_quality_debt(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "def f():\n"
        "    try:\n"
        "        print('x')\n"
        "    except Exception:\n"
        "        print('bad')\n"
        + "\n".join(f"    x{i} = {i}" for i in range(45))
        + "\n",
        encoding="utf-8",
    )

    metrics = collect_metrics([tmp_path])

    assert metrics.long_functions_gt40 == 1
    assert metrics.broad_exceptions == 1
    assert metrics.print_calls == 2
