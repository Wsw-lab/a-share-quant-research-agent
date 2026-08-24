from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicDemoTest(unittest.TestCase):
    def test_sample_panel_is_deterministic_in_separate_process(self) -> None:
        command = (
            "from a_share_quant_agent.sample_data import make_sample_panel; "
            "a=make_sample_panel(start='2024-01-01',end='2024-06-30',symbols=8); "
            "b=make_sample_panel(start='2024-01-01',end='2024-06-30',symbols=8); "
            "assert a.equals(b); assert len(a)>0; "
            "assert {'date','symbol','open','close','amount','roe','pe'}.issubset(a.columns)"
        )

        completed = subprocess.run(
            [sys.executable, "-c", command],
            cwd=ROOT,
            env=_source_environment(),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_public_demo_runs_end_to_end(self) -> None:
        completed = subprocess.run(
            [sys.executable, "examples/run_demo.py"],
            cwd=ROOT,
            env=_source_environment(),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("Strategy:", completed.stdout)
        self.assertIn("Report:", completed.stdout)


def _source_environment() -> dict[str, str]:
    environment = dict(os.environ)
    source = str(ROOT / "src")
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = source if not existing else os.pathsep.join([source, existing])
    return environment


if __name__ == "__main__":
    unittest.main()
