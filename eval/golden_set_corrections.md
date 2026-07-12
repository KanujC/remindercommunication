# Golden set corrections

Per CLAUDE.md 9.1: "Bootstrap the CSV with Claude, then hand-correct every row and commit
the corrected version. The diff between generated and corrected is kept here as evidence
of the review."

## Review pass

The bootstrap CSV (50 rows: 36 core + 6 breadth + 8 adversarial) was generated
programmatically from fixed per-segment customer profiles (`SEGMENT_PROFILES` in the
generation script) so that `segment_expected` is reproducible from the segmentation rules
in CLAUDE.md 5.1, rather than typed by hand per row.

Verification run against the real `segment_customer()` implementation
(`dunning_studio.segmentation`):

- All 49 valid rows: `segment_customer(customer) == segment_expected`. No mismatches.
- `adv-050` (the row-invalid case, empty `due_date`): confirmed it raises
  `InvalidRowError` in `dunning_studio.eval_loader.row_to_case`, matching its
  `expected_outcome=invalid` and the CLAUDE.md 9.1 requirement that this row exercises
  the schema-rejection path rather than the pass/fallback/held pipeline.

## Corrections made

- None required — the bootstrap profiles were chosen deliberately at the segmentation
  boundary midpoints (not on the 0.70 / 0.95 / 7 / 2 boundaries themselves), so no row
  landed in an ambiguous segment. Boundary values are covered separately and exactly by
  the unit tests in `tests/test_segmentation.py` (`0.70`, `0.95`, `7.0`/`7.01`, `1`/`2`
  `prior_defaults`), per the CLAUDE.md 5.1 instruction to unit-test those boundaries
  explicitly rather than through the golden set.

## Known limitation flagged by design (not a correction)

- `adv-047` (`Blacklist Records GmbH` as `merchant_name`) is deliberately
  `expected_outcome=held`, not `fallback`. Gate A5 is a case-insensitive **substring**
  match against the blocklist term `blacklist`, so a legitimate merchant name containing
  that substring trips A5 on the generated text *and* on the static template (both inject
  `{{MERCHANT_NAME}}` into the sign-off). Since the static-template fallback step also
  fails its own A1..A6 check, the pipeline correctly routes to `held` rather than
  producing an unsendable "static_template" decision — verified against the real
  pipeline, not assumed. This is the documented limitation called out in CLAUDE.md 9.1
  ("the report must show it, documented limitation, not silent") and tracked as an open
  question in CLAUDE.md 13 (moving A5 to token-boundary matching). We do not "fix" the
  false positive here because fixing it is the open design question, not a golden-set bug.
