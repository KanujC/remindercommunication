#!/usr/bin/env python3
"""Golden-set eval runner. Plain Python, no framework. See CLAUDE.md section 9.

Usage:
    python eval/run_eval.py [--live] [--judge] [--golden-set PATH] [--concurrency N]

Without --live, uses a MockLLMClient that echoes a template-shaped response (so the
harness and report machinery can be exercised without network access / an API key).
With --live, calls the real Anthropic API via DUNNING_MODEL / ANTHROPIC_API_KEY and is
the run whose report.md/report.json must be committed alongside any prompt/policy change
per I7.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dunning_studio.eval_loader import InvalidRowError, read_rows, row_to_case  # noqa: E402
from dunning_studio.gates.deterministic import SEVERITY  # noqa: E402
from dunning_studio.llm import AnthropicLLMClient, MockLLMClient  # noqa: E402
from dunning_studio.pipeline import run_case  # noqa: E402
from dunning_studio.schemas import SendDecision  # noqa: E402
from dunning_studio.segmentation import segment_customer  # noqa: E402
from dunning_studio.template_loader import validate_all_templates  # noqa: E402

RETRIES = 2
CONCURRENCY_DEFAULT = 4


_MOCK_EMAIL_BODY = {
    "en-GB": (
        "Hello,\n\nThis concerns invoice {{ACCOUNT_REF}} for {{AMOUNT}}, due on {{DUE_DATE}}, "
        "which is still outstanding today. {{DISCLOSURE}} Please settle it soon using the link "
        "below whenever you have a moment to do so.\n\n{{PAY_LINK}}\n\nRegards,\n{merchant}"
    ),
    "de-DE": (
        "Hallo,\n\nes geht um die Rechnung {{ACCOUNT_REF}} über {{AMOUNT}}, fällig am "
        "{{DUE_DATE}}, die noch immer offen ist. {{DISCLOSURE}} Bitte begleichen Sie den Betrag "
        "bald über den folgenden Link, sobald Sie einen Moment Zeit dafür finden.\n\n{{PAY_LINK}}"
        "\n\nMit freundlichen Grüßen,\n{merchant}"
    ),
    "nl-NL": (
        "Hallo,\n\ndit gaat over factuur {{ACCOUNT_REF}} van {{AMOUNT}}, met vervaldatum "
        "{{DUE_DATE}}, die nog altijd openstaat. {{DISCLOSURE}} Betaal deze binnenkort via "
        "onderstaande link zodra u daar een moment voor heeft.\n\n{{PAY_LINK}}\n\n"
        "Met vriendelijke groet,\n{merchant}"
    ),
    "sv-SE": (
        "Hej,\n\ndetta gäller fakturan {{ACCOUNT_REF}} på {{AMOUNT}}, med förfallodatum "
        "{{DUE_DATE}}, som fortfarande är obetald. {{DISCLOSURE}} Betala snart via länken "
        "nedan när du har en stund över för det.\n\n{{PAY_LINK}}\n\nMed vänliga hälsningar,\n{merchant}"
    ),
}

_MOCK_SMS_BODY = {
    "en-GB": "Invoice {{ACCOUNT_REF}} for {{AMOUNT}}, due {{DUE_DATE}}, is outstanding. {{DISCLOSURE}} Pay: {{PAY_LINK}} - {merchant}",
    "de-DE": "Rechnung {{ACCOUNT_REF}} über {{AMOUNT}}, fällig {{DUE_DATE}}, ist offen. {{DISCLOSURE}} Zahlen: {{PAY_LINK}} - {merchant}",
    "nl-NL": "Factuur {{ACCOUNT_REF}} van {{AMOUNT}}, vervaldatum {{DUE_DATE}}, staat open. {{DISCLOSURE}} Betaal: {{PAY_LINK}} - {merchant}",
    "sv-SE": "Fakturan {{ACCOUNT_REF}} på {{AMOUNT}}, förfallodatum {{DUE_DATE}}, är obetald. {{DISCLOSURE}} Betala: {{PAY_LINK}} - {merchant}",
}


def _mock_response_for(row: dict) -> str:
    """A locale-appropriate template-shaped body used only for --live-less smoke runs of the
    harness. It exercises the harness/report machinery, not tone quality (that needs --live)."""
    table = _MOCK_EMAIL_BODY if row["channel"] == "email" else _MOCK_SMS_BODY
    return table[row["locale"]].replace("{merchant}", row["merchant_name"])


@dataclass
class CaseOutcome:
    case_id: str
    ok: bool
    detail: str
    decision: SendDecision | None = None
    segment_ok: bool = True
    outcome_ok: bool = True


def _observed_outcome(decision: SendDecision) -> str:
    return {"generated": "pass", "regenerated": "pass", "static_template": "fallback", "held": "held"}[
        decision.source
    ]


def run_one(row: dict, client_factory, judge_enabled: bool) -> CaseOutcome:
    case_id = row["case_id"]
    try:
        customer, merchant, facts = row_to_case(row)
    except InvalidRowError as exc:
        expected = row.get("expected_outcome", "")
        ok = expected == "invalid"
        return CaseOutcome(case_id, ok, f"schema rejection ({'expected' if ok else 'UNEXPECTED'}): {exc}")

    segment_ok = segment_customer(customer) == row["segment_expected"]

    client = client_factory(row)
    last_exc: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            decision = run_case(case_id, customer, merchant, facts, client, judge_enabled=judge_enabled)
            break
        except (TimeoutError, ConnectionError) as exc:  # transport errors only, never gate failures
            last_exc = exc
            time.sleep(0.5 * (attempt + 1))
    else:
        return CaseOutcome(case_id, False, f"transport error after {RETRIES} retries: {last_exc}")

    observed = _observed_outcome(decision)
    outcome_ok = observed == row["expected_outcome"]
    ok = segment_ok and outcome_ok
    detail = f"segment={'ok' if segment_ok else 'MISMATCH'} outcome={observed} (expected {row['expected_outcome']})"
    return CaseOutcome(case_id, ok, detail, decision=decision, segment_ok=segment_ok, outcome_ok=outcome_ok)


def relational_r3_fact_stability(outcomes: list[CaseOutcome], rows_by_id: dict[str, dict]) -> bool:
    """R3: amount and date strings must be byte-identical across all messages of a family."""
    from dunning_studio.schemas import format_amount, format_due_date

    ok = True
    for outcome in outcomes:
        if outcome.decision is None:
            continue
        row = rows_by_id[outcome.case_id]
        _, _, facts = row_to_case(row)
        expected_amount = format_amount(facts.amount_minor, facts.currency, facts.locale)
        expected_date = format_due_date(facts.due_date, facts.locale)
        if expected_amount not in outcome.decision.final_text or expected_date not in outcome.decision.final_text:
            if outcome.decision.source != "held":  # held text may be a rejected draft
                ok = False
    return ok


def build_report(outcomes: list[CaseOutcome], rows_by_id: dict[str, dict], run_id: str, model: str) -> dict:
    total = len(outcomes)
    passed = sum(1 for o in outcomes if o.ok)
    fallback_count = sum(
        1 for o in outcomes if o.decision is not None and o.decision.source == "static_template"
    )
    held_count = sum(1 for o in outcomes if o.decision is not None and o.decision.source == "held")

    check_failures: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.decision is None:
            continue
        for check in outcome.decision.gate_result.checks:
            if not check.passed:
                check_failures[check.check_id] = check_failures.get(check.check_id, 0) + 1

    adversarial_rows = [cid for cid, row in rows_by_id.items() if row.get("adversarial") == "true"]
    adversarial_ok = all(o.outcome_ok for o in outcomes if o.case_id in adversarial_rows)

    non_adversarial = [o for o in outcomes if o.case_id not in adversarial_rows]
    hard_check_failures_non_adv = 0
    for outcome in non_adversarial:
        if outcome.decision is None:
            continue
        hard_check_failures_non_adv += sum(
            1 for c in outcome.decision.gate_result.checks
            if not c.passed and SEVERITY.get(c.check_id, "hard") == "hard"
        )

    r3_ok = relational_r3_fact_stability(outcomes, rows_by_id)

    return {
        "run_id": run_id,
        "model": model,
        "total_cases": total,
        "pass_rate": passed / total if total else 0.0,
        "fallback_rate": (fallback_count + held_count) / total if total else 0.0,
        "held_count": held_count,
        "static_template_count": fallback_count,
        "check_failures": check_failures,
        "adversarial_outcome_match": adversarial_ok,
        "hard_check_failures_non_adversarial": hard_check_failures_non_adv,
        "relational_r3_fact_stability": r3_ok,
        "failed_cases": [
            {"case_id": o.case_id, "detail": o.detail} for o in outcomes if not o.ok
        ],
    }


def render_markdown(report: dict) -> str:
    lines = [f"# Eval report — {report['run_id']}", ""]
    if report["model"] == "mock":
        lines += [
            "> **Mock-mode run.** No live model calls were made; this exercises the harness, "
            "gate wiring, and report machinery only. It does not certify tone quality. Run "
            "`python eval/run_eval.py --live` with `ANTHROPIC_API_KEY` set for the report that "
            "gates a merge per CLAUDE.md I7 / 9.5.",
            "",
        ]
    lines += [
        f"- model: `{report['model']}`",
        f"- total cases: {report['total_cases']}",
        f"- pass rate: {report['pass_rate']:.1%}",
        f"- fallback rate (static + held): {report['fallback_rate']:.1%}",
        f"- held count: {report['held_count']}",
        f"- adversarial expected_outcome matched exactly: {report['adversarial_outcome_match']}",
        f"- hard-check failures on non-adversarial cases: {report['hard_check_failures_non_adversarial']}",
        f"- R3 fact stability: {report['relational_r3_fact_stability']}",
        "",
        "## Per-check failure counts",
        "",
    ]
    if report["check_failures"]:
        for check_id, count in sorted(report["check_failures"].items()):
            lines.append(f"- {check_id}: {count}")
    else:
        lines.append("- none")
    lines += ["", "## Failed cases", ""]
    if report["failed_cases"]:
        for case in report["failed_cases"]:
            lines.append(f"- `{case['case_id']}`: {case['detail']}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden-set", default=str(Path(__file__).parent / "golden_set.csv"))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY_DEFAULT)
    args = parser.parse_args()

    validate_all_templates()
    from langdetect import detect_langs

    detect_langs("warm up langdetect's lazy global init before spawning worker threads")

    rows = read_rows(Path(args.golden_set))
    rows_by_id = {r["case_id"]: r for r in rows}

    if args.live:
        model = AnthropicLLMClient().model
        client_factory = lambda row: AnthropicLLMClient()  # noqa: E731
    else:
        model = "mock"
        client_factory = lambda row: MockLLMClient(  # noqa: E731
            responses=[_mock_response_for(row)] * 3
        )

    outcomes: list[CaseOutcome] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(run_one, row, client_factory, args.judge): row["case_id"] for row in rows}
        for future in as_completed(futures):
            outcomes.append(future.result())
    outcomes.sort(key=lambda o: o.case_id)

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    report = build_report(outcomes, rows_by_id, run_id, model)

    (Path(__file__).parent / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (Path(__file__).parent / "report.md").write_text(render_markdown(report), encoding="utf-8")

    print(f"pass_rate={report['pass_rate']:.1%} fallback_rate={report['fallback_rate']:.1%} "
          f"held={report['held_count']} adversarial_ok={report['adversarial_outcome_match']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
