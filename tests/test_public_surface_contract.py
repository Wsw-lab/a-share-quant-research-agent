from __future__ import annotations

import ast
import configparser
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.public_surface_policy import scan_sensitive_text


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
EXPECTED_ACTION_PINS = {
    "actions/checkout": ("v4", "11d5960a326750d5838078e36cf38b85af677262"),
    "actions/setup-python": ("v5", "a26af69be951a213d495a4c3e4e4022e16d87065"),
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
    "studies/pit_factor_replication_v1/plan.json",
    "src/a_share_quant_agent/confirmatory_study.py",
    "src/a_share_quant_agent/reproducible_experiment.py",
)
MAINTAINED_PUBLIC_MODULES = [
    "audit",
    "backtest",
    "confirmatory_study",
    "qdata_snapshot",
    "report",
    "reproducible_experiment",
    "sample_data",
    "spec",
]
PYTHON_PATH_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py)(?![A-Za-z0-9_-])"
)
_QDATA_BUILDER_REFERENCE = "build_" + "research_snapshot" + ".py"
_QDATA_MODULE_REFERENCE = "research_" + "snapshot" + ".py"
EXTERNAL_PYTHON_REFERENCES = {
    (
        "src/a_share_quant_agent/reproducible_experiment.py",
        _QDATA_BUILDER_REFERENCE,
    ),
    (
        "src/a_share_quant_agent/reproducible_experiment.py",
        _QDATA_MODULE_REFERENCE,
    ),
    (
        "tests/fixtures/QDATA_RESEARCH_SNAPSHOT_PROVENANCE.md",
        f"examples/{_QDATA_BUILDER_REFERENCE}",
    ),
}


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


def _local_python_reference_exists(source: Path, reference: str) -> bool:
    if "/" in reference:
        return (ROOT / reference).is_file()
    candidates = (
        source.parent / reference,
        ROOT / reference,
        ROOT / "examples" / reference,
        ROOT / "tests" / reference,
        PACKAGE / reference,
    )
    return any(candidate.is_file() for candidate in candidates)


def _readme_green_path_commands(text: str) -> str:
    match = re.search(
        r"## 全新 checkout 的唯一离线绿色路径.*?```bash\n(?P<commands>.*?)\n```",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError("README green-path bash block is missing")
    return match.group("commands")


def _workflow_payload() -> dict[str, object]:
    lines = [
        line
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    payload = json.loads("\n".join(lines))
    if not isinstance(payload, dict):
        raise AssertionError("workflow root must be a mapping")
    return payload


def _workflow_uses(value: object) -> list[str]:
    uses: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "uses" and isinstance(child, str):
                uses.append(child)
            else:
                uses.extend(_workflow_uses(child))
    elif isinstance(value, list):
        for child in value:
            uses.extend(_workflow_uses(child))
    return uses


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
        commands = _readme_green_path_commands(text)
        self.assertTrue(commands.startswith("set -euo pipefail\n"))
        self.assertIn("export PYTHONDONTWRITEBYTECODE=1", commands)
        self.assertIn("git remote get-url origin", commands)
        self.assertIn("https://github.com/Wsw-lab/a-share-quant-research-agent", commands)
        self.assertIn('test -z "$(git status --short --untracked-files=all)"', commands)
        self.assertIn("规范 GitHub origin", text)
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

    def test_readme_green_path_runs_verbatim_in_a_clean_canonical_checkout(self) -> None:
        if os.environ.get("AGENT_README_GREEN_PATH_CHILD") == "1":
            self.skipTest("avoid recursively executing the README path")

        commands = _readme_green_path_commands(README.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp_dir:
            checkout = Path(temp_dir) / "checkout"
            checkout.mkdir()
            for source in _tracked_files():
                relative = source.relative_to(ROOT)
                target = checkout / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

            setup_commands = (
                ["git", "init", "--quiet"],
                ["git", "add", "."],
                [
                    "git",
                    "-c",
                    "user.name=Public Surface Contract",
                    "-c",
                    "user.email=contract@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "fixture checkout",
                ],
                [
                    "git",
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/Wsw-lab/a-share-quant-research-agent.git",
                ],
            )
            for command in setup_commands:
                subprocess.run(command, cwd=checkout, check=True, capture_output=True, text=True)

            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            environment["AGENT_README_GREEN_PATH_CHILD"] = "1"
            environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
            completed = subprocess.run(
                ["bash", "-c", commands],
                cwd=checkout,
                env=environment,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            )
            status = subprocess.run(
                ["git", "status", "--short", "--untracked-files=all"],
                cwd=checkout,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.stdout, "")
            self.assertEqual(list(checkout.rglob("__pycache__")), [])
            self.assertEqual(list(checkout.rglob("*.egg-info")), [])

    def test_readme_origin_guard_accepts_canonical_https_and_ssh_forms_only(self) -> None:
        commands = _readme_green_path_commands(README.read_text(encoding="utf-8"))
        guard, separator, _remainder = commands.partition('AGENT_RUN_ROOT="$(mktemp -d)"')
        self.assertTrue(separator)
        accepted = (
            "https://github.com/Wsw-lab/a-share-quant-research-agent",
            "https://github.com/Wsw-lab/a-share-quant-research-agent.git",
            "git@github.com:Wsw-lab/a-share-quant-research-agent.git",
            "ssh://git@github.com/Wsw-lab/a-share-quant-research-agent",
            "ssh://git@github.com/Wsw-lab/a-share-quant-research-agent.git",
        )
        rejected = (
            "https://github.com/other-owner/a-share-quant-research-agent.git",
            "ssh://git@example.invalid/Wsw-lab/a-share-quant-research-agent.git",
        )
        for origin in (*accepted, *rejected):
            with self.subTest(origin=origin), tempfile.TemporaryDirectory() as temp_dir:
                checkout = Path(temp_dir)
                subprocess.run(["git", "init", "--quiet"], cwd=checkout, check=True)
                subprocess.run(["git", "remote", "add", "origin", origin], cwd=checkout, check=True)
                completed = subprocess.run(
                    ["bash", "-c", guard],
                    cwd=checkout,
                    capture_output=True,
                    text=True,
                )
                expected = 0 if origin in accepted else 2
                self.assertEqual(completed.returncode, expected, completed.stderr)

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

    def test_package_all_is_the_exact_maintained_importable_surface(self) -> None:
        package = importlib.import_module("a_share_quant_agent")
        self.assertEqual(package.__all__, MAINTAINED_PUBLIC_MODULES)
        for module_name in package.__all__:
            with self.subTest(module=module_name):
                importlib.import_module(f"a_share_quant_agent.{module_name}")

    def test_all_tracked_python_command_and_path_references_resolve(self) -> None:
        violations: list[str] = []
        text_suffixes = {
            ".cfg", ".csv", ".html", ".ini", ".ipynb", ".json", ".md",
            ".py", ".toml", ".txt", ".yaml", ".yml",
        }
        for path in _tracked_files():
            if path.suffix.lower() not in text_suffixes and path.name != ".gitignore":
                continue
            relative_source = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            for match in PYTHON_PATH_REFERENCE.finditer(text):
                reference = match.group(1)
                if (relative_source, reference) in EXTERNAL_PYTHON_REFERENCES:
                    continue
                if _local_python_reference_exists(path, reference):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{relative_source}:{line}: {reference}")
        self.assertEqual(violations, [], "unresolved tracked Python references")

    def test_declared_required_package_modules_exist(self) -> None:
        violations: list[str] = []
        for path in sorted(PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                if not any(isinstance(target, ast.Name) and target.id == "required_modules" for target in node.targets):
                    continue
                if not isinstance(node.value, (ast.List, ast.Tuple)):
                    continue
                for item in node.value.elts:
                    if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                        continue
                    if item.value.endswith(".py") and not (path.parent / item.value).is_file():
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {item.value}")
        self.assertEqual(violations, [], "missing required package modules")

    def test_legacy_scheduler_and_completion_builder_fail_closed_without_side_effects(self) -> None:
        ops = importlib.import_module("a_share_quant_agent.ops")
        readiness = importlib.import_module("a_share_quant_agent.completion_readiness")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            reports_root = temp_root / "reports"
            with self.assertRaisesRegex(RuntimeError, "not a maintained public workflow"):
                ops.run_scheduler_once(
                    reports_root,
                    config_path=temp_root / "missing-config.yaml",
                    dry_run=True,
                )
            self.assertFalse(reports_root.exists())
            with self.assertRaisesRegex(RuntimeError, "not a maintained public workflow"):
                readiness.build_completion_readiness(reports_root)
            self.assertFalse(reports_root.exists())

    def test_removed_daily_pipeline_config_is_not_presented_as_runnable(self) -> None:
        self.assertFalse((ROOT / "configs" / "daily_pipeline.yaml").exists())

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
        text_suffixes = {
            ".cfg", ".csv", ".html", ".ini", ".ipynb", ".json", ".md",
            ".py", ".toml", ".txt", ".yaml", ".yml",
        }
        for path in _tracked_files():
            if path.suffix.lower() not in text_suffixes and path.name != ".gitignore":
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                stale_paths = () if path.resolve() == Path(__file__).resolve() else STALE_GENERATED
                self.assertEqual(scan_sensitive_text(text, stale_paths=stale_paths), ())

    def test_sensitive_text_scanner_rejects_cross_platform_paths_and_secret_families(self) -> None:
        windows_forward = "C:" + "/workspace/private.csv"
        windows_backward = "D:" + "\\workspace\\private.csv"
        private_headers = {
            "generic-private-key": "-----" + "BEGIN PRIVATE KEY" + "-----",
            "rsa-private-key": "-----" + "BEGIN RSA PRIVATE KEY" + "-----",
            "openssh-private-key": "-----" + "BEGIN OPENSSH PRIVATE KEY" + "-----",
            "ec-private-key": "-----" + "BEGIN EC PRIVATE KEY" + "-----",
            "dsa-private-key": "-----" + "BEGIN DSA PRIVATE KEY" + "-----",
        }
        classic_github_tokens = {
            prefix: "g" + prefix + "_" + ("A" * 36)
            for prefix in ("hp", "ho", "hu", "hs", "hr")
        }
        malicious_samples = {
            "posix-macos": "/" + "Users" + "/reviewer/private.csv",
            "posix-linux": "/" + "home" + "/runner/private.csv",
            "windows-forward": windows_forward,
            "windows-backward": windows_backward,
            **private_headers,
            **{f"github-classic-{name}": value for name, value in classic_github_tokens.items()},
            "github-fine-grained": "git" + "hub_pat_" + ("B" * 48),
            "openai-token": "s" + "k-" + ("C" * 32),
            "aws-access-key": "A" + "KIA" + ("D" * 16),
            "generic-secret-assignment": "api_" + "key = '" + ("E" * 24) + "'",
        }
        for name, sample in malicious_samples.items():
            with self.subTest(sample=name):
                self.assertTrue(scan_sensitive_text(sample), name)

    def test_sensitive_text_scanner_does_not_treat_url_schemes_as_windows_drives(self) -> None:
        benign_samples = (
            "https://github.com/Wsw-lab/a-share-quant-research-agent",
            "http://example.invalid/research",
            "ssh://git@example.invalid/repository",
            "C: is a prose label without an absolute path",
            "relative/path/to/data.csv",
        )
        for sample in benign_samples:
            with self.subTest(sample=sample):
                self.assertEqual(scan_sensitive_text(sample), ())

    def test_runtime_outputs_are_ignored_but_fixtures_and_templates_are_not(self) -> None:
        runtime_outputs = (
            ".research-artifacts/demo/demo_report.md",
            "reports/demo_report.md",
            "reports/strategy_factory/runs/example/report.md",
            "snapshots/example/manifest.json",
            "cache/provider/response.json",
            "data_assets/manifests/production_import/generated.json",
            "data_assets/market/daily_quotes.csv",
            "build/lib/example" + ".py",
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
        workflow = _workflow_payload()
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
        workflow = _workflow_payload()
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

    def test_all_nonlocal_workflow_actions_are_sha_pinned_to_verified_major_refs(self) -> None:
        workflow_text = WORKFLOW.read_text(encoding="utf-8")
        workflow = _workflow_payload()
        uses = _workflow_uses(workflow)
        self.assertGreater(len(uses), 0)
        observed: dict[str, str] = {}
        for value in uses:
            if value.startswith("./"):
                continue
            with self.subTest(uses=value):
                match = re.fullmatch(r"([^@\s]+)@([0-9a-f]{40})", value)
                self.assertIsNotNone(match, "nonlocal workflow actions must use a full commit SHA")
                if match is not None:
                    observed[match.group(1)] = match.group(2)

        self.assertEqual(
            observed,
            {action: sha for action, (_tag, sha) in EXPECTED_ACTION_PINS.items()},
        )
        for action, (tag, _sha) in EXPECTED_ACTION_PINS.items():
            self.assertIn(f"# {action} {tag}", workflow_text)


if __name__ == "__main__":
    unittest.main()
