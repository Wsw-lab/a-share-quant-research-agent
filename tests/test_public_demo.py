from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicDemoTest(unittest.TestCase):
    def test_source_checkout_sample_panel_is_deterministic_in_separate_process(self) -> None:
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

    def test_source_checkout_public_demo_runs_end_to_end(self) -> None:
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

    def test_installed_package_imports_and_runs_probe_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            target = temporary / "site-packages"
            outside = temporary / "outside-repository"
            outside.mkdir()
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            environment["PIP_NO_INDEX"] = "1"
            install = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "--no-build-isolation",
                    "--target",
                    str(target),
                    str(ROOT),
                ],
                cwd=outside,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(install.returncode, 0, install.stdout + install.stderr)

            probe_environment = dict(environment)
            probe_environment["PYTHONPATH"] = str(target)
            probe = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        "import a_share_quant_agent as package; "
                        "from a_share_quant_agent.sample_data import make_sample_panel; "
                        f"target=Path({str(target)!r}).resolve(); "
                        "module=Path(package.__file__).resolve(); "
                        "assert target in module.parents, (target,module); "
                        "panel=make_sample_panel(start='2024-01-01',end='2024-01-05',symbols=2); "
                        "assert len(panel)==10; assert panel['symbol'].nunique()==2"
                    ),
                ],
                cwd=outside,
                env=probe_environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)


def _source_environment() -> dict[str, str]:
    environment = dict(os.environ)
    source = str(ROOT / "src")
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = source if not existing else os.pathsep.join([source, existing])
    return environment


if __name__ == "__main__":
    unittest.main()
