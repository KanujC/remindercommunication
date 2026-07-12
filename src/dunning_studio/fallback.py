"""Fallback ladder: regenerate -> static template -> hold. See CLAUDE.md section 8.
No file IO here (I/O lives in pipeline.py per working rule 12); this module returns data
for pipeline.py to persist.
"""

from dunning_studio.gates.deterministic import run_all as run_deterministic_checks
from dunning_studio.gates.judge import judge_passes, run_judge
from dunning_studio.generator import REGENERATE_TEMPERATURE, generate
from dunning_studio.injection import build_tokens, inject
from dunning_studio.llm import LLMClient
from dunning_studio.schemas import GateCheck, GateResult, InvoiceFacts, ToneSpec
from dunning_studio.template_loader import load_static_template

HIGH_VALUE_THRESHOLD_MINOR = 50_000


def is_high_value(facts: InvoiceFacts) -> bool:
    return facts.amount_minor >= HIGH_VALUE_THRESHOLD_MINOR


def gate_text(
    text: str,
    facts: InvoiceFacts,
    tone_spec: ToneSpec,
    customer_name: str,
    merchant_name: str,
    client: LLMClient | None,
    judge_enabled: bool,
) -> tuple[GateResult, int]:
    """Run deterministic checks, then the judge if enabled and deterministic hard checks pass."""
    checks = run_deterministic_checks(text, facts, tone_spec, customer_name, merchant_name)
    hard_failed = any(not c.passed for c in checks if _is_hard(c.check_id))
    model_calls = 0
    judge_scores: dict[str, int] | None = None

    if judge_enabled and not hard_failed and client is not None:
        judge_scores = run_judge(client, text, tone_spec)
        model_calls += 1
        passed_judge = judge_scores is not None and judge_passes(judge_scores)
        checks.append(
            GateCheck(
                check_id="J1",
                passed=passed_judge,
                detail=f"scores={judge_scores}",
            )
        )

    soft_failed = any(not c.passed for c in checks if not _is_hard(c.check_id) and c.check_id != "J1")
    judge_failed = judge_enabled and not hard_failed and (
        judge_scores is None or not judge_passes(judge_scores)
    )
    passed = not hard_failed and not soft_failed and not judge_failed
    return GateResult(passed=passed, checks=checks, judge_scores=judge_scores), model_calls


def _is_hard(check_id: str) -> bool:
    from dunning_studio.gates.deterministic import SEVERITY, HARD

    return SEVERITY.get(check_id, HARD) == HARD


def regenerate_step(
    client: LLMClient,
    customer_name: str,
    merchant_name: str,
    facts: InvoiceFacts,
    tone_spec: ToneSpec,
    failed_checks: list[GateCheck],
    judge_enabled: bool,
) -> tuple[str, GateResult, int]:
    """Fallback ladder step 1: regenerate at temperature 0 with failed checks as constraints."""
    raw = generate(
        client, customer_name, merchant_name, facts, tone_spec,
        temperature=REGENERATE_TEMPERATURE, failed_checks=failed_checks,
    )
    tokens = build_tokens(customer_name, merchant_name, facts)
    text = inject(raw, tokens)
    gate_result, judge_calls = gate_text(
        text, facts, tone_spec, customer_name, merchant_name, client, judge_enabled
    )
    return text, gate_result, 1 + judge_calls


def static_template_step(
    tone_spec: ToneSpec,
    facts: InvoiceFacts,
    customer_name: str,
    merchant_name: str,
) -> tuple[str, GateResult]:
    """Fallback ladder step 2. A1..A6 must pass by construction (I5); failure here is a bug."""
    from dunning_studio.gates.deterministic import (
        check_a1_amount, check_a2_due_date, check_a3_account_ref,
        check_a4_no_unresolved_tokens, check_a5_blocklist, check_a6_disclosure,
    )

    raw = load_static_template(tone_spec.segment, facts.locale, facts.channel)
    tokens = build_tokens(customer_name, merchant_name, facts)
    text = inject(raw, tokens)
    checks = [
        check_a1_amount(text, facts),
        check_a2_due_date(text, facts),
        check_a3_account_ref(text, facts),
        check_a4_no_unresolved_tokens(text),
        check_a5_blocklist(text),
        check_a6_disclosure(text, facts),
    ]
    failures = [c for c in checks if not c.passed]
    if failures:
        detail = "; ".join(f"{c.check_id}: {c.detail}" for c in failures)
        raise RuntimeError(f"static template failed gates (should be impossible, I5): {detail}")
    return text, GateResult(passed=True, checks=checks, judge_scores=None)
