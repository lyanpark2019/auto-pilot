from __future__ import annotations

from pathlib import Path

import pytest

from scripts.quality.metric_snapshot import collect_metrics


def test_collect_metrics_counts_quality_debt(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import subprocess\n\n"
        "def f():\n"
        "    event('sample.start')\n"
        "    subprocess.run(['ok'], timeout=1)\n"
        "    subprocess.check_output(['bad'])\n"
        "    subprocess.run('bad', shell=True, timeout=1)\n"
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
    assert metrics.subprocess_without_timeout == 1
    assert metrics.shell_true_calls == 1
    assert metrics.event_calls == 1


@pytest.mark.parametrize(
    ("rel_path", "expected_prints"),
    [("prod.py", 1), ("test_prod.py", 0), ("pkg/tests/prod.py", 0)],
)
def test_collect_metrics_excludes_test_files(tmp_path: Path, rel_path: str, expected_prints: int) -> None:
    sample = tmp_path / rel_path
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text("def f():\n    print('x')\n", encoding="utf-8")

    metrics = collect_metrics([tmp_path])

    assert metrics.print_calls == expected_prints


@pytest.mark.parametrize(
    ("call", "expected_missing_timeout"),
    [
        ("subprocess.run(['x'])", 1),
        ("subprocess.check_call(['x'], timeout=1)", 0),
        ("subprocess.Popen(['x'])", 0),
    ],
)
def test_collect_metrics_counts_subprocess_timeout_debt(
    tmp_path: Path,
    call: str,
    expected_missing_timeout: int,
) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(f"import subprocess\ndef f():\n    {call}\n", encoding="utf-8")

    metrics = collect_metrics([tmp_path])

    assert metrics.subprocess_without_timeout == expected_missing_timeout


@pytest.mark.parametrize(
    ("call", "expected_shell_true"),
    [("helper(shell=True)", 1), ("helper(shell=False)", 0), ("helper()", 0)],
)
def test_collect_metrics_counts_shell_true(tmp_path: Path, call: str, expected_shell_true: int) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(f"def f():\n    {call}\n", encoding="utf-8")

    metrics = collect_metrics([tmp_path])

    assert metrics.shell_true_calls == expected_shell_true
