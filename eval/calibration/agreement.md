# Judge calibration: agreement report

Status: **not yet run.** Per CLAUDE.md 9.6, this requires:

1. 30 hand-scored outputs from a **live** eval run (`python eval/run_eval.py --live --judge`)
   recorded in `hand_scores.csv` using the same rubric as `prompts/judge_v1.md`.
2. Exact and within-1 agreement per dimension (`register_match`, `firmness_accuracy`,
   `brand_voice`, `dignity`) between the hand scores and the judge's scores for the same
   30 cases.
3. A one-line disposition for every disagreement of 2+ points: judge wrong, human wrong,
   or rubric ambiguous. Rubric ambiguities produce rubric v2 and a re-run.

This step needs a real `ANTHROPIC_API_KEY` and a human reviewer and could not be completed
in this environment. `hand_scores.csv` is scaffolded with the correct header so the
calibration run has somewhere to write to. Recalibrate on any judge-prompt or judge-model
change (9.6.4).
