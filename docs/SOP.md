# Standard operating procedure

1. Confirm scope: identify changes in recorded contractual ip rights with exact source evidence. Read the README's limitations first.
2. Run the documented sample command. The sample is synthetic and licensed for reuse.
3. Open the review HTML. Inspect classification, evidence and configuration before
   accepting any finding. An observed/calculated value is conditional on supplied inputs.
4. For a draft outside the grammar, first create an analysis of a supported schedule or
prepare a register against `schema/rights.schema.json`. Edit the exported rights JSON,
preserving the source byte hash and exact evidence spans. Re-run compare with
`--before-register before-rights.json --after-register after-rights.json`. All stated
values need evidence and all source text needs a coverage disposition. Attribute a
human-confirmed reading with a reviewer; a name is an attestation, not authentication.

Offsets count zero-based Unicode characters after UTF-8 BOM removal, with an exclusive
end. Hashes cover raw bytes, including line endings. Evidence coverage establishes
provenance and accounting, not the correctness of the legal interpretation.
5. Assess every finding. Dismiss false positives with reasons; use correction overlays
   for your replacement assessment; use needs-information for unresolved evidence.
6. Identify the responsible reviewer and review basis. Download decisions. Real matters
   require the actual responsible person's decision; test sign-offs are synthetic only.
7. Finalize into a new directory. The CLI verifies the exact package and complete decision
   set. A mismatched fingerprint, changed source or missing decision is refused.
8. Verify the reviewed export. Retain the original analysis and decision history.
9. Hand off the usable output: `before-rights.json`, `after-rights.json`, an evidence-linked `report.json`, `report.md`, `findings.sarif` and `review.html`.
10. Confirm any external business outcome separately. Exporting a report makes no
    external change and grants no rights, compliance certification or survey authority.
