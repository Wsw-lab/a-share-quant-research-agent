from __future__ import annotations

import ast
import configparser
import importlib
import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PORTFOLIO = ROOT / "PROJECT_PORTFOLIO.md"
DATA_AVAILABILITY = ROOT / "DATA_AVAILABILITY.md"
CHECKLIST = ROOT / "GITHUB_SUBMISSION_CHECKLIST.md"
LEGACY_NOTE = ROOT / "docs" / "legacy-evidence.md"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
TOOLCHAIN = ROOT / ".github" / "ci-toolchain.txt"
RUNTIME = ROOT / ".github" / "ci-runtime.txt"
PACKAGE = ROOT / "src" / "a_share_quant_agent"

EXPECTED_TOOLCHAIN = {
    "packaging": "26.3",
    "pip": "26.2.1",
    "setuptools": "84.0.0",
    "wheel": "0.48.0",
}
EXPECTED_RUNTIME = {
    "numpy": "2.0.2",
    "pandas": "2.3.3",
    "python-dateutil": "2.9.0.post0",
    "pytz": "2026.3.post1",
    "six": "1.17.0",
    "tzdata": "2026.3",
}
STALE_GENERATED = (
    "reports/completion_readiness/latest_readiness.json",
    "reports/completion_readiness/latest_readiness.md",
    "reports/portfolio_readiness/latest_portfolio_readiness.json",
    "reports/portfolio_readiness/latest_portfolio_readiness.md",
    "reports/strategy_factory/latest_board.json",
    "reports/strategy_factory/latest_board.md",
    "data_assets/manifests/production_import/data_asset_inventory.json",
    "data_assets/manifests/production_import/data_asset_inventory.md",
    "data_assets/manifests/production_import/production_asset_validation.json",
    "data_assets/manifests/production_import/production_asset_validation.md",
)
MAINTAINED_FILES = (
    "examples/run_demo.py",
    "examples/strategy_specs/quality_value_momentum.json",
    "src/a_share_quant_agent/reproducible_experiment.py",
)


def _exact_pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_-]+)==([A-Za-z0-9_.+-]+)", stripped)
        if not match:
            raise AssertionError(f"CI requirement is not an exact pin: {stripped}")
        pins[match.group(1).lower().replace("_", "-")] = match.group(2)
    return pins


def _tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    paths = [ROOT / value.decode("utf-8") for value in result.stdout.split(b"\0") if value]
    return [path for path in paths if path.is_file()]


def _is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", path],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


class ReadmeContractTest(unittest.TestCase):
    def test_readme_opens_with_a_bounded_evidence_matrix(self) -> None:
        text = README.read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertLessEqual(len(lines), 220)
        self.assertTrue(lines[0].startswith("# "))
        self.assertIn("| 能力 | 证据级别 |", "\n".join(lines[:12]))
        for level in ("implemented", "unit-tested", "local-integration-tested", "open"):
            self.assertIn(f"`{level}`", text)
        self.assertIn("A 股研究/审计原型", text)
        self.assertIn("research_snapshot_v1", text)
        self.assertIn("独立验证器", text)
        self.assertIn("t 日收盘决策 → t+1 原始开盘参考 → 显式摩擦 → 成交", text)

    def test_readme_has_one_exact_offline_green_path(self) -> None:
        text = README.read_text(encoding="utf-8")
        self.assertEqual(text.count("## 全新 checkout 的唯一离线绿色路径"), 1)
        self.assertEqual(text.count("```bash"), 1)
        required_commands = (
            "python3 examples/run_demo.py",
            "python3 -m a_share_quant_agent.reproducible_experiment run",
            "--snapshot-dir tests/fixtures/qdata_research_snapshot_v1",
            "--qdata-sha 1111111111111111111111111111111111111111",
            "diff -r",
            "python3 -m a_share_quant_agent.reproducible_experiment verify",
            "python3 -m unittest discover -s tests -p 'test_*.py'",
        )
        for command in required_commands:
            self.assertIn(command, text)

    def test_readme_states_receipt_verdict_and_evidence_boundaries(self) -> None:
        text = README.read_text(encoding="utf-8")
        for marker in (
            "INSUFFICIENT_EVIDENCE",
            "2 个标的、3 个交易会话",
            "样本外",
            "统计推断",
            "券商",
            "实盘交易",
            "数据权利",
            "覆盖率",
            "PostgreSQL",
            "cross-store transactions",
            "GitHub Actions",
        ):
            self.assertIn(marker, text)
        self.assertIn("不声称远端工作流已经运行", text)
        for forbidden in (
            "portfolio-ready",
            "production-ready",
            "stable candidate",
            "validated production returns",
        ):
            self.assertNotIn(forbidden, text.lower())
        self.assertNotRegex(text, r"(?i)(annualized return|max drawdown|sharpe)\s*[:：]\s*[-+]?\d")

    def test_all_relative_readme_links_resolve(self) -> None:
        text = README.read_text(encoding="utf-8")
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
        self.assertGreaterEqual(len(links), 4)
        for target in links:
            if re.match(r"^[a-z]+://", target) or target.startswith("#"):
                continue
            clean_target = target.split("#", 1)[0]
            with self.subTest(target=target):
                self.assertTrue((ROOT / clean_target).exists())


class MaintainedSurfaceContractTest(unittest.TestCase):
    def test_only_the_explicit_maintained_examples_are_public_commands(self) -> None:
        for relative in MAINTAINED_FILES:
            self.assertTrue((ROOT / relative).is_file(), relative)
        self.assertEqual(
            {path.name for path in (ROOT / "examples").glob("*.py")},
            {"run_demo.py"},
        )
        demo = (ROOT / "examples" / "run_demo.py").read_text(encoding="utf-8")
        self.assertIn("synthetic engine demonstration only", demo)
        self.assertIn(".research-artifacts", demo)
        self.assertIn('print(f"Report: {report_relative.as_posix()}")', demo)
        self.assertNotIn("Annualized return:", demo)
        self.assertNotIn("Max drawdown:", demo)
        tree = ast.parse(demo)
        maintained_imports = sorted(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("a_share_quant_agent.")
        )
        self.assertGreater(len(maintained_imports), 0)
        for module_name in maintained_imports:
            with self.subTest(maintained_import=module_name):
                importlib.import_module(module_name)

    def test_package_all_exactly_matches_importable_module_files(self) -> None:
        package = importlib.import_module("a_share_quant_agent")
        expected = []
        for path in sorted(PACKAGE.glob("*.py")):
            if path.name == "__init__.py":
                continue
            try:
                importlib.import_module(f"a_share_quant_agent.{path.stem}")
            except (ImportError, ModuleNotFoundError):
                continue
            expected.append(path.stem)
        self.assertEqual(package.__all__, expected)
        for module_name in package.__all__:
            with self.subTest(module=module_name):
                importlib.import_module(f"a_share_quant_agent.{module_name}")

    def test_generated_evidence_is_removed_and_explained(self) -> None:
        for relative in STALE_GENERATED:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists())
        note = LEGACY_NOTE.read_text(encoding="utf-8")
        self.assertIn("Git history", note)
        self.assertIn("不能验证修正后的执行引擎", note)
        self.assertIn("省略的输入", note)
        self.assertNotRegex(note, r"[-+]?\d+(?:\.\d+)?%")

        public_surfaces = (README, PORTFOLIO, DATA_AVAILABILITY, CHECKLIST, LEGACY_NOTE, WORKFLOW)
        for path in public_surfaces:
            text = path.read_text(encoding="utf-8")
            with self.subTest(no_stale_link=path.relative_to(ROOT)):
                for relative in STALE_GENERATED:
                    self.assertNotIn(relative, text)

    def test_portfolio_data_and_checklist_share_the_public_boundary(self) -> None:
        documents = (PORTFOLIO, DATA_AVAILABILITY, CHECKLIST)
        for path in documents:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("research_snapshot_v1", text)
                self.assertIn("INSUFFICIENT_EVIDENCE", text)
                for forbidden in (
                    "portfolio-ready",
                    "production-ready",
                    "stable candidate",
                    "validated production returns",
                ):
                    self.assertNotIn(forbidden, text.lower())
        checklist = CHECKLIST.read_text(encoding="utf-8")
        self.assertIn("python3 -m unittest -v tests.test_public_surface_contract", checklist)
        self.assertNotIn("Showcase ready: True", checklist)


class RepositoryHygieneContractTest(unittest.TestCase):
    def test_tracked_text_has_no_machine_paths_or_secret_like_values(self) -> None:
        slash = "/"
        local_roots = (
            slash + "Users" + slash,
            slash + "home" + slash,
        )
        windows_drive = re.compile(r"[A-Za-z]:" + re.escape("\\"))
        token_prefix = "s" + "k" + "-"
        aws_prefix = "A" + "K" + "I" + "A"
        private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
        assignment = re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password)\b"
            r"\s*[:=]\s*[\"'][^\"']{12,}[\"']"
        )
        text_suffixes = {
            ".cfg", ".csv", ".html", ".ini", ".ipynb", ".json", ".md",
            ".py", ".toml", ".txt", ".yaml", ".yml",
        }
        for path in _tracked_files():
            if path.suffix.lower() not in text_suffixes and path.name != ".gitignore":
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                for root in local_roots:
                    self.assertNotIn(root, text)
                self.assertIsNone(windows_drive.search(text))
                self.assertNotRegex(text, re.escape(token_prefix) + r"[A-Za-z0-9_-]{20,}")
                self.assertNotRegex(text, re.escape(aws_prefix) + r"[0-9A-Z]{16}")
                self.assertNotIn(private_key_marker, text)
                self.assertIsNone(assignment.search(text))
                if path.resolve() != Path(__file__).resolve():
                    for stale_path in STALE_GENERATED:
                        self.assertNotIn(stale_path, text)

    def test_runtime_outputs_are_ignored_but_fixtures_and_templates_are_not(self) -> None:
        runtime_outputs = (
            ".research-artifacts/demo/demo_report.md",
            "reports/demo_report.md",
            "reports/strategy_factory/runs/example/report.md",
            "snapshots/example/manifest.json",
            "cache/provider/response.json",
            "data_assets/manifests/production_import/generated.json",
            "data_assets/market/daily_quotes.csv",
            "build/lib/example.py",
            "dist/package.whl",
            "src/example.egg-info/PKG-INFO",
            ".env.local",
            "local-panel.parquet",
        )
        for relative in runtime_outputs:
            with self.subTest(runtime=relative):
                self.assertTrue(_is_ignored(relative))
        preserved = (
            "tests/fixtures/qdata_research_snapshot_v1/manifest.json",
            "tests/fixtures/qdata_research_snapshot_v1/daily_bar.csv",
            "data_assets/templates/daily_quotes.csv",
            "examples/strategy_specs/quality_value_momentum.json",
            ".env.example",
        )
        for relative in preserved:
            with self.subTest(preserved=relative):
                self.assertFalse(_is_ignored(relative))


class CiContractTest(unittest.TestCase):
    def test_ci_is_parseable_read_only_and_matches_supported_python(self) -> None:
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(set(workflow["on"]), {"push", "pull_request"})
        job = workflow["jobs"]["offline-verification"]
        self.assertEqual(job["strategy"]["matrix"]["python-version"], ["3.10", "3.11", "3.12"])
        self.assertLessEqual(job["timeout-minutes"], 20)

        setup = configparser.ConfigParser()
        setup.read(ROOT / "setup.cfg", encoding="utf-8")
        self.assertEqual(setup["options"]["python_requires"].strip(), ">=3.10,<3.13")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('"setuptools>=83"', pyproject)
        readme = README.read_text(encoding="utf-8")
        self.assertIn("Python 3.10–3.12", readme)

    def test_ci_steps_cover_the_complete_offline_evidence_chain_in_order(self) -> None:
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        steps = workflow["jobs"]["offline-verification"]["steps"]
        names = [step["name"] for step in steps]
        expected_order = [
            "Checkout",
            "Set up Python",
            "Install pinned packaging toolchain",
            "Verify packaging toolchain versions",
            "Install pinned runtime dependencies",
            "Install package without dependency resolution",
            "Verify installed package import outside checkout",
            "Run public-surface contract",
            "Run complete offline unittest suite",
            "Run maintained public demo",
            "Run strict experiment twice and verify",
            "Prove receipt tamper rejection",
            "Check repository diff",
        ]
        self.assertEqual(names, expected_order)
        by_name = {step["name"]: step for step in steps}
        outside = by_name["Verify installed package import outside checkout"]
        self.assertEqual(outside["working-directory"], "${{ runner.temp }}")
        experiment = by_name["Run strict experiment twice and verify"]["run"]
        for marker in (
            "--qdata-sha 1111111111111111111111111111111111111111",
            "diff -r",
            "--expected-agent-sha",
            "--expected-qdata-sha",
        ):
            self.assertIn(marker, experiment)
        self.assertIn("git diff --check", by_name["Check repository diff"]["run"])
        tamper = by_name["Prove receipt tamper rejection"]["run"]
        self.assertIn('b"fixture_arithmetic_only", b"fixture_arithmetic_onlz"', tamper)
        self.assertIn("TAMPER_EXIT=$?", tamper)
        self.assertIn('test "$TAMPER_EXIT" -eq 2', tamper)

    def test_ci_uses_exact_toolchains_and_no_external_market_or_mutating_actions(self) -> None:
        self.assertEqual(_exact_pins(TOOLCHAIN), EXPECTED_TOOLCHAIN)
        self.assertEqual(_exact_pins(RUNTIME), EXPECTED_RUNTIME)
        workflow_text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--disable-pip-version-check --no-deps -r .github/ci-toolchain.txt", workflow_text)
        self.assertIn("--only-binary=:all: --no-deps -r .github/ci-runtime.txt", workflow_text)
        self.assertIn("--no-index --no-deps --no-build-isolation -e .", workflow_text)
        for forbidden in (
            "tushare",
            "akshare",
            "docker",
            "broker",
            "publish",
            "git push",
            "pull_request_target",
            "secrets.",
        ):
            self.assertNotIn(forbidden, workflow_text.lower())


if __name__ == "__main__":
    unittest.main()
