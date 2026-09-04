# Stage 2 Preparation and Paper Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish every Stage-2 preparation artifact that can be completed before a data provider responds, while preserving the outcome-blind boundary and producing a journal-readable pre-results paper with fixed result shells.

**Architecture:** Keep the existing tested `a_share_quant_agent.study_v2_coverage` module as the sole authoritative full-delivery coverage script and document its two-pass review workflow rather than adding a competing runner. Keep provider-neutral protocols and blank forms in Git, place provider-specific second-round email material outside every Git worktree, and extend the manuscript source plus deterministic DOCX builder with pre-specified result shells. Registration and execution authorization remain human-controlled, null until their chronology gates are satisfied, and fail closed in the existing runner.

**Tech Stack:** Python 3.10-3.12, `unittest`, Markdown, JSON templates, `python-docx`, LibreOffice rendering through the bundled document runtime, Git.

**Spec:** `studies/pit_factor_bias_decomposition_v2/statistical_analysis_plan.md`

## Global Constraints

- The confirmatory analysis interval remains 1 January 2010 through 31 December 2022, with quote endpoints through 31 January 2023 and warm-up from 1 January 2009.
- No Stage-2 factor, return, IC, ranking, portfolio outcome, or variant comparison may be computed, retained, released, or inspected before external registration and execution authorization.
- The registered design remains 18 variants, four factors, 72 reporting cells, one primary estimand, 28 Benjamini-Hochberg secondary estimands, and two deterministic isolation checks.
- Provider-specific correspondence, identities, negotiation records, quotations, and replies remain outside Git; contracts, accounts, credentials, and licensed rows are never public.
- The authoritative coverage report, review attestation, timestamp evidence, registration working files, authorization consumption record, and Stage-2 output directory remain outside every Git worktree.
- Existing public templates remain null until the external facts they represent have occurred and have been independently verified.
- Document generation uses the bundled workspace runtime and ends with DOCX render, inspection of every page, accessibility audit, and PDF regeneration from the accepted DOCX.

---

### Task 1: Prepare the private second-round provider package

**Files:**
- Create privately: `<private-outreach-root>/<provider-a>/00_Reply_Email.txt`
- Create privately: `<private-outreach-root>/<provider-a>/SEND_CHECKLIST.txt`
- Create privately: `<private-outreach-root>/<provider-b>/00_Reply_Email.txt`
- Create privately: `<private-outreach-root>/<provider-b>/SEND_CHECKLIST.txt`
- Copy privately: the five provider-neutral technical request, rights, mapping, handoff, and acceptance files already tracked under `studies/pit_factor_bias_decomposition_v2/`

**Interfaces:**
- Consumes: a positive or information-seeking provider reply.
- Produces: a private attachment set that asks only for capability, rights, delivery, and review information and contains no result-bearing sample request.

- [x] **Step 1: Create the two provider-specific reply email texts**

Write concise replies that acknowledge interest, state that the study remains pre-results, list the five technical attachments, and ask the provider to return a completed field-mapping workbook plus written rights answers.

- [x] **Step 2: Create the two private send checklists**

Require a positive provider reply, removal of unneeded attachments, confirmation that no contract or credential is attached, and retention of the sent message in private correspondence storage.

- [x] **Step 3: Copy the public blank technical files into each private second-round directory**

Use provider-neutral filenames and preserve the tracked source bytes so the private copies can be compared by SHA-256.

- [x] **Step 4: Verify privacy and package contents**

Run:

```bash
find <private-outreach-root> -type f -maxdepth 2 -print
stat -f '%Sp %N' <private-outreach-root> <private-outreach-root>/<provider-a> <private-outreach-root>/<provider-b>
git status --short --untracked-files=all
```

Expected: both provider directories contain one reply, one checklist, and five technical attachments; directories are mode `0700`, files are mode `0600`, and Git reports none of these private files.

### Task 2: Publish the coverage execution and acceptance runbook

**Files:**
- Create: `studies/pit_factor_bias_decomposition_v2/coverage_execution_and_acceptance_runbook.md`
- Modify: `studies/pit_factor_bias_decomposition_v2/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: four canonical provider-delivery CSV files, a completed rights attestation, a completed human review attestation, and private output paths.
- Produces: an exact metadata-audit command, an authoritative coverage command, an acceptance matrix tied to existing gate identifiers, and explicit stop conditions.

- [x] **Step 1: Write the two-pass operator procedure**

Document Pass A using `a_share_quant_agent.data_access` and Pass B using `a_share_quant_agent.study_v2_coverage`, including exact commands, permitted observations, prohibited observations, private-path rules, and exit-code meaning.

- [x] **Step 2: Add the acceptance matrix**

Map data interval, 156 monthly signals, exact `t/t+1/t+20/t+21` endpoints, minimum 1,000 complete identifiers, publication-date coverage, lifecycle integrity, official calendar, amount units, ST and suspension semantics, supplier-recorded suspension valuation, identifier stability, rights, and reviewer attestation to pass/fail decisions.

- [x] **Step 3: Link the runbook from both READMEs**

Describe the module as the existing authoritative execution script and state that no delivery currently passes because no contracted data have been accepted.

- [x] **Step 4: Verify the existing code contract**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -B -m unittest tests.test_data_access tests.test_study_v2_coverage tests.test_public_receipt_privacy
```

Expected: all tests pass with no Stage-2 outcome computation.

### Task 3: Complete the external registration and authorization operator packet

**Files:**
- Create: `studies/pit_factor_bias_decomposition_v2/registration_and_authorization_runbook.md`
- Create: `studies/pit_factor_bias_decomposition_v2/external_registration_submission_text.md`
- Modify: `studies/pit_factor_bias_decomposition_v2/external_registration_handoff.md`
- Modify: `studies/pit_factor_bias_decomposition_v2/README.md`

**Interfaces:**
- Consumes: a passing bounded probe receipt, passing full coverage and rights evidence, a signed prior-exposure attestation, frozen plan core, clean code commit, and complete design manifest.
- Produces: provider-neutral submission prose, a field-by-field registration receipt checklist, an independent-verification checklist, and a post-verification authorization checklist.

- [x] **Step 1: Write the registration submission text**

State the research question, observed-pilot disclosure, 2010-2022 historical confirmation, one primary, 28 secondaries, 72-cell full disclosure, outcome-blind status conditions, data-rights boundary, and the exact manifest-or-digest attachment rule.

- [x] **Step 2: Write the chronology runbook**

Fix the sequence `coverage and rights review -> prior exposure attestation -> frozen plan core -> design manifest -> external provider record -> independent verification -> registration receipt -> execution authorization -> final execution envelope` and explain which private or public bytes each stage binds.

- [x] **Step 3: Add explicit no-go examples**

Reject a Git commit timestamp, local file modification time, sent email, mutable cloud file, unverifiable private record, changed post-submission manifest, self-signed placeholder, and authorization signed before registration verification.

- [x] **Step 4: Verify template and runner consistency**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -B -m unittest tests.test_external_registration_handoff tests.test_authorization_consumption tests.test_execution_fail_closed
```

Expected: all tests pass, and no template changes status from draft or prepared to registered or authorized.

### Task 4: Add fixed result shells and rebuild the paper

**Files:**
- Create: `studies/pit_factor_bias_decomposition_v2/prespecified_results_tables.md`
- Modify: `studies/pit_factor_bias_decomposition_v2/stage1_manuscript.md`
- Modify: `studies/pit_factor_bias_decomposition_v2/build_stage1_manuscript.py`
- Create: `tests/test_stage1_manuscript_artifact.py`
- Regenerate: `docs/working-paper/A_Share_Factor_Specification_Effects_Stage1_Manuscript.docx`
- Regenerate: `docs/working-paper/A_Share_Factor_Specification_Effects_Stage1_Manuscript.pdf`
- Modify: `README.md`

**Interfaces:**
- Consumes: the existing manuscript source, existing protocol-based builder, fixed estimand inventory, and existing figure assets.
- Produces: a pre-results paper with a compact primary/secondary reporting shell in the main text and a complete machine-checkable 72-cell plus 28-secondary supplement, with every empirical entry marked unestimated.

- [x] **Step 1: Write the failing artifact test**

```python
from pathlib import Path
import unittest
from docx import Document
from docx.oxml.ns import qn


ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "docs/working-paper/A_Share_Factor_Specification_Effects_Stage1_Manuscript.docx"


class Stage1ManuscriptArtifactTest(unittest.TestCase):
    def test_docx_contains_result_shell_and_uses_plain_black_heading_system(self) -> None:
        doc = Document(DOCX)
        text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
        self.assertIn("Pre-specified historical result shell", text)
        self.assertIn("Not yet estimated", text)
        title = next(paragraph for paragraph in doc.paragraphs if paragraph.style.name == "Title")
        title_borders = title._p.pPr.find(qn("w:pBdr")) if title._p.pPr is not None else None
        self.assertIsNone(title_borders)
        for style_name in ("Title", "Subtitle", "Heading 1", "Heading 2", "Heading 3"):
            color = doc.styles[style_name].font.color.rgb
            self.assertEqual(str(color), "000000")


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the artifact test and verify the expected failure**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -B -m unittest tests.test_stage1_manuscript_artifact
```

Expected: fail because the current DOCX has no historical result shell and uses colored heading styles and a title border.

- [x] **Step 3: Add the main-text result shell and complete supplement**

Add a compact table covering the primary contrast, ordered common-support components, grouped secondary families, deterministic checks, sample months, and evidence status. Generate the supplement with all 72 fixed factor-variant rows, all 28 fixed secondary rows, exposure diagnostics, endpoint completeness fields, and `Not yet estimated` in every empirical field.

- [x] **Step 4: Update the DOCX builder**

Remove the title border and boxed manuscript-status treatment, set title and heading styles to black, preserve readable table borders and widths, and support the new result-shell table columns without shrinking body text further.

- [x] **Step 5: Mark the document edit operation and rebuild with the bundled runtime**

Run:

```bash
<bundled-node> <document-skill>/container_tools/mark_artifact_operation_started.mjs --operation-kind edit --expected-output-count 1 --output-format docx
<bundled-python> studies/pit_factor_bias_decomposition_v2/build_stage1_manuscript.py
```

Expected: the deterministic DOCX builder exits zero and overwrites only the tracked manuscript DOCX and generated figure assets.

- [x] **Step 6: Run the artifact test and manuscript consistency checks**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -B -m unittest tests.test_stage1_manuscript_artifact tests.test_confirmatory_study tests.test_stage2_estimands
```

Expected: all tests pass; no result field contains a historical Stage-2 estimate.

- [x] **Step 7: Render and inspect every page**

Run the bundled DOCX renderer with PDF emission enabled, inspect every page PNG at 100 percent zoom, correct any clipping, overlap, broken table, font substitution, or page-break defect, then copy the accepted rendered PDF to the tracked working-paper path.

- [x] **Step 8: Run accessibility and metadata checks**

Run the bundled accessibility audit and confirm the DOCX contains no author identity, credential, private path, or unfilled author placeholder.

### Task 5: Final verification and GitHub synchronization

**Files:**
- Review every file changed in Tasks 1-4.

**Interfaces:**
- Consumes: completed public artifacts, verified private package, accepted DOCX/PDF render, and passing tests.
- Produces: one auditable Git commit on `main` and a synchronized `origin/main`.

- [x] **Step 1: Review the public/private boundary**

Run:

```bash
git status --short --untracked-files=all
git diff --check
git diff --stat
```

Expected: only provider-neutral public files, tests, manuscript source, builder, DOCX/PDF, and README changes appear; no provider-specific email, identity, quote, correspondence, contract, credential, or licensed data appears.

- [ ] **Step 2: Run the complete offline verification under a compliant Python runtime**

Run:

```bash
PATH="<bundled-python-bin>:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src <bundled-python> -B -m unittest discover -s tests -p 'test_*.py'
```

Expected: all applicable tests pass; environment-only skips are reported explicitly.

- [x] **Step 3: Verify document artifacts one final time**

Confirm the latest render page count, inspect every page PNG, run the accessibility audit, and compare the manuscript's reported page count in `README.md` with the rendered PDF.

- [ ] **Step 4: Commit the public changes**

```bash
git add README.md docs/superpowers/plans/2026-09-04-stage2-preparation-and-paper.md docs/working-paper/A_Share_Factor_Specification_Effects_Stage1_Manuscript.docx docs/working-paper/A_Share_Factor_Specification_Effects_Stage1_Manuscript.pdf studies/pit_factor_bias_decomposition_v2 tests/test_stage1_manuscript_artifact.py
git commit -m "research: complete Stage-2 preparation materials"
```

- [ ] **Step 5: Push and verify synchronization**

```bash
git push origin main
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

Expected: the two revisions are identical and the worktree is clean.
