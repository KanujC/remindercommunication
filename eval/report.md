# Eval report — 20260712T094031Z

> **Mock-mode run.** No live model calls were made; this exercises the harness, gate wiring, and report machinery only. It does not certify tone quality. Run `python eval/run_eval.py --live` with `ANTHROPIC_API_KEY` set for the report that gates a merge per CLAUDE.md I7 / 9.5.

- model: `mock`
- total cases: 50
- pass rate: 100.0%
- fallback rate (static + held): 2.0%
- held count: 1
- adversarial expected_outcome matched exactly: True
- hard-check failures on non-adversarial cases: 0
- R3 fact stability: True

## Per-check failure counts

- A5: 1

## Failed cases

- none
