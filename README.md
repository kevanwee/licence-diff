# licence-diff

[![Checks](https://github.com/kevanwee/licence-diff/actions/workflows/ci.yml/badge.svg)](https://github.com/kevanwee/licence-diff/actions/workflows/ci.yml)

**Identify changes in recorded contractual IP rights with exact source evidence.** A standalone CLI and offline evidence-review workspace for IP lawyers, publishers and contract reviewers.

![Local review workspace](docs/images/review.png)

## A complete sample matter

Two campaign-illustration licence schedules change adaptation rights, territory, media, exclusivity, sublicensing, duration, restrictions and the definition of the work.

The primary outputs are `before-rights.json`, `after-rights.json`, an evidence-linked `report.json`, `report.md`, `findings.sarif` and `review.html`.

## Install and run

Requires Python 3.11 or later. Clone this repository and work from its root:

```bash
git clone https://github.com/kevanwee/licence-diff.git
cd licence-diff
python -m venv .venv
```

Activate with `source .venv/bin/activate` on macOS/Linux or
`.venv\Scripts\Activate.ps1` in PowerShell, then:

```bash
python -m pip install .
python -m licence_diff compare examples/campaign-licence/before.txt examples/campaign-licence/after.txt --matter "Campaign illustrations" --synthetic --out out/change
python -m licence_diff verify out/change
```

Open `out/change/review.html` in your browser. The CLI and review run offline after
installation. No model API key, account, server or sibling project is required.
Samples describe fictional future drafts and plans; they make no claim of actual
execution, legal effectiveness or current law. See [sample licensing](examples/NOTICE.md).

## Complete the review

1. Inspect every finding, its classification, before/after values and source evidence.
2. Confirm, dismiss, correct the assessment, or record that more information is needed.
   Add a reason for every decision. A correction is an explicit reviewer overlay;
   original observations and source files stay intact.
3. Enter the reviewer's name/role, basis and authority. Download `review-decisions.json`.
   Names are supplied attestations, not authenticated identity or decision rights.
4. Place the downloaded decision in the repository root, then run:

```bash
python -m licence_diff finalize out/change --decisions review-decisions.json --out out/reviewed
python -m licence_diff verify out/reviewed
```

The final directory contains `report.html`, reviewed JSON/Markdown/SARIF, decisions,
source snapshots and a receipt hashing the exported files. Pending questions retain
`needs-information` status. Even a completed review can confirm unresolved substantive
problems; review completion does not mean compliance, a cleared licence or a correct
lease. No external system is changed.

Reports include configuration, the CI threshold, runtime versions, source hashes, source locators, scope assumptions and
review status. Package fingerprints bind decisions to the exact saved analysis. An
edited source, configuration or extraction requires a new analysis and new decisions.
Old output directories are never overwritten. The review renderer is versioned with
the engine; retain the same engine version when verifying old packages.

## Error and CI behaviour

Exit **0** means the requested analysis/export succeeded; it is not a legal clearance.
Use `--fail-on info`, `--fail-on warning` or `--fail-on error` for an explicit CI gate.
Exit **1** means findings reached that threshold; the report is still exported.
Exit **2** means invalid inputs or a refused operation, including stale/incomplete
decisions. Argument-parser errors also return 2. Default `--fail-on none` permits
interactive exploration without treating findings as an execution failure.

Unknown keys and schema versions are refused. JSON duplicate keys and non-finite
numbers are refused. A failed build publishes no partial matter directory. No-op
comparisons still produce an inspectable report; no findings does not establish legal
adequacy. Hashes detect accidental alteration, not malicious rewriting of all hashes
or independent source authenticity.

Keep original analysis packages alongside reviewed exports. These files can contain
confidential matter data. This repository's `.gitignore` excludes `out/`; choose local
storage consistent with your organisation's requirements. No data is uploaded by the tool.

## Development and verification

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m pip wheel . --no-deps --wheel-dir dist
```

Versioned schemas are in `schema/`; `python -m licence_diff schema NAME` prints them.
CI runs Python 3.11/3.14 on Linux and Windows. Tests cover deterministic domain logic,
the complete analysis/review/export journey, invalid inputs, tampering, correction
overlays and preserved originals. See [acceptance evidence](docs/ACCEPTANCE.md) and
[the walkthrough](docs/SOP.md).

## Licence

MIT. The synthetic sample data and plan artwork are also MIT-licensed. Dependency
licences remain with their respective projects. No real client documents are included.

## Scope and method

Version one supports saved UTF-8 text and a **labelled licence schedule** grammar.
It recognises `Grant:`, `Work:`, `Licensor:`, `Licensee:`, `Rights:`, `Territories:`,
`Media:`, `Exclusive:`, `Sublicensing:`, `Term:`, `Restrictions:` and `Definition X:`.
Semicolon-separated values form sets; yes/no/unknown are explicit. Fixed terms use
`YYYY-MM-DD to YYYY-MM-DD`; perpetual and unknown are separate states.

Rights vocabulary: reproduce, distribute, adapt, communicate, perform, display.
Media vocabulary: print, web, social, paid-advertising, broadcast, internal.
Territories require explicit uppercase two-letter labels. Regional shorthand such as
APAC stays unresolved. Missing permission is never interpreted as unrestricted use.

The synthetic example uses a copyright licence. This MVP does not implement patent
claim analysis, trade mark similarity, fair-use judgments or arbitrary PDF/DOCX OCR.
Unrecognised prose remains a source-linked review finding; contradictory duplicate
fields are refused. Every non-whitespace source character must be accounted for.

Extraction is proposed interpretation, not a verified legal fact. Comparisons recognise
set expansion/narrowing, fixed-term window changes, changed parties/works, definitions
and restrictions. Qualifying language can defeat an apparent expansion and requires
the responsible lawyer's judgment.

## Correcting source facts

For a draft outside the grammar, first create an analysis of a supported schedule or
prepare a register against `schema/rights.schema.json`. Edit the exported rights JSON,
preserving the source byte hash and exact evidence spans. Re-run compare with
`--before-register before-rights.json --after-register after-rights.json`. All stated
values need evidence and all source text needs a coverage disposition. Attribute a
human-confirmed reading with a reviewer; a name is an attestation, not authentication.

Offsets count zero-based Unicode characters after UTF-8 BOM removal, with an exclusive
end. Hashes cover raw bytes, including line endings. Evidence coverage establishes
provenance and accounting, not the correctness of the legal interpretation.

## Invalid and contradictory inputs

Duplicate/conflicting schedule fields, missing parties/work, reversed fixed dates, unsupported structured values, duplicate grants, altered source hashes, mismatching quotations and unaccounted source text are rejected. Unsupported prose and unknown scopes become visible findings.


## Optional browser regression

Install the developer browser tool locally:

```bash
npm install --prefix out/browser-tools playwright
npx --prefix out/browser-tools playwright install chromium
node scripts/verify_browser.mjs
```

The script uses your active `python` by default (`PROJECT_PYTHON` can select another).
It runs a synthetic analysis, desktop/mobile checks, an incomplete-review refusal,
downloads a synthetic corrected decision, finalizes it and verifies the exported report.
It creates a fresh namespace under `out/` and refreshes the README screenshot.
For a standalone distribution check, build a wheel and run `scripts/smoke_wheel.py
--wheel PATH_TO_WHEEL`. That test creates a clean environment outside the source tree.


## Harder subject matter

A larger synthetic matter, independent expected-result ledger and complete review/export
rehearsal are included. See [complex matter verification](docs/COMPLEX-TEST.md) for results,
known limitations and the one-command walkthrough. Version 0.1.1 preserves earlier
released artifacts; use the corresponding engine release to verify older analysis packages.
