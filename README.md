# Dunning Studio

A tone-adaptive payment-reminder pipeline: synthetic customer + merchant + invoice inputs
in, a gated, tone-matched reminder out — always with a full decision trace.

> Open-source reconstruction, from first principles and with fully synthetic data, of a
> tone-adaptive payment-communication pattern. No proprietary prompts, thresholds,
> merchant data, or customer data. See `CLAUDE.md` for the full technical design spec —
> this README is the quickstart.

## What it does

1. Derives a **customer segment** from payment history (deterministic rules, no ML).
2. Resolves a **target tone** from segment × merchant archetype × reminder index.
3. Generates a tone-matched reminder with an LLM — the model only ever writes tone; the
   amount, due date, account reference, and payment link never touch it (they're opaque
   placeholder tokens, injected afterwards by string substitution).
4. Runs the output through a **validation gate**: 10 deterministic asserts (A1..A10) plus
   an LLM tone judge.
5. On failure, walks a **fallback ladder**: regenerate once → pre-approved static
   template → hold for human review. Step 2 always succeeds by construction, so every
   case ends in a sendable message or an explicit hold — never silence.
6. Emits a `SendDecision` with the full gate trace.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# Run the offline demo (mock LLM client, no network / API key needed)
.venv/bin/dunning demo

# Run one golden-set case
.venv/bin/dunning run core-001

# Run the full golden-set eval (mock mode: exercises the harness, not tone quality)
.venv/bin/python eval/run_eval.py

# Run tests
.venv/bin/pytest
```

To use the real model, set `ANTHROPIC_API_KEY` (and optionally `DUNNING_MODEL`) and pass
`--live` to `dunning demo`, `dunning run`, or `eval/run_eval.py`.

## Demo trace

`dunning demo` prints, in order: the resolved `ToneSpec`, every gate check with
pass/fail and its detail string, the fallback decision, and the final text. Example
(mock client, `friendly`/`defaulter`/firmness 4):

```
ToneSpec
  segment=defaulter archetype=friendly firmness=4
  register_notes: First person plural, contractions allowed, warm but concise, at most one exclamation mark, no emoji.

Gate checks
  [PASS] A1: expected='€49.00' occurrences=1 other_matches=[]
  [PASS] A2: expected='15 June 2026' occurrences=1 other_matches=[]
  ...
  [PASS] A10: phrase_hits=[] ngram_hits=[]

Fallback
  source=generated fallback_steps_taken=0 model_calls=1 latency_ms=290

Final text
Hi Alex, ...
```

## Repository layout

See CLAUDE.md section 10 for the full layout and section 11 for build-milestone history.
Key entry points:

- `src/dunning_studio/pipeline.py` — orchestrates one case end to end (`run_case`).
- `src/dunning_studio/gates/deterministic.py` — A1..A10.
- `src/dunning_studio/gates/judge.py` — LLM tone judge, defensive JSON parsing.
- `src/dunning_studio/fallback.py` — the regenerate → static → hold ladder.
- `src/dunning_studio/cli.py` — `dunning demo` / `dunning run <case_id>`.
- `eval/run_eval.py` — golden-set runner; `eval/golden_set.csv` is the 50-case set.

## Status against CLAUDE.md thresholds (9.5)

The eval report committed at `eval/report.md`/`report.json` is a **mock-mode** run (no
`ANTHROPIC_API_KEY` was available in the environment this was built in): it validates the
harness, gate wiring, and fallback ladder end to end, and confirms all 8 adversarial
cases resolve to their designed `expected_outcome`. It does **not** certify tone quality
— that requires `--live` against the real model, plus the judge-calibration pass in
`eval/calibration/` (not yet run, see `eval/calibration/agreement.md`).
