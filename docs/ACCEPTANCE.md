# Product acceptance

| Requirement | Evidence |
| --- | --- |
| Stranger can install/run | README quickstart; clean wheel smoke test |
| Realistic licensed sample | examples/, examples/NOTICE.md |
| Input to exported output | tests/test_review.py full CLI journey; browser decision download |
| Inspect/correct findings | offline HTML review, correction overlays, source revision workflow |
| Invalid/missing/contradictory inputs | domain negative tests and documented error handling |
| Deterministic unit/end-to-end tests | tests/test_engine.py, tests/test_review.py, CI matrix |
| References/configuration/status retained | frozen snapshots, report.json, package digest, review receipt |
| Facts/assumptions/judgments distinguished | finding classifications, source evidence and scope statements |

Current execution evidence is in verification.json. Synthetic practice does not establish
legal adequacy, authenticated reviewer authority or actual business outcomes.
