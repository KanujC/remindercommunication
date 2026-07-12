"""Fallback ladder: regenerate -> static template -> hold. See CLAUDE.md section 8.
No file IO here (I/O lives in pipeline.py per working rule 12); this module returns data
for pipeline.py to persist.
"""

from dunning_studio.gates.deterministic import run_all, run_static_checks
from dunning_studio.gates.judge import judge_checks, run_judge
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
    """Run A1..A10, then the tone judge only if all deterministic checks pass — the judge costs
    a model call and text that already fails deterministically is headed for the ladder anyway
    (CLAUDE.md 7: cheap asserts first, judge last)."""
    checks = run_all(text, facts, tone_spec, customer_name, merchant_name)
    model_calls = 0
    judge_scores: dict[str, int] | None = None

    if judge_enabled and client is not None and all(c.passed for c in checks):
        judge_scores = run_judge(client, text, tone_spec)
        model_calls += 1
        checks.extend(judge_checks(judge_scores))

    passed = all(c.passed for c in checks)
    return GateResult(passed=passed, checks=checks, judge_scores=judge_scores), model_calls


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
    raw = load_static_template(tone_spec.segment, facts.locale, facts.channel)
    tokens = build_tokens(customer_name, merchant_name, facts)
    text = inject(raw, tokens)
    checks = run_static_checks(text, facts)
    failures = [c for c in checks if not c.passed]
    if failures:
        detail = "; ".join(f"{c.check_id}: {c.detail}" for c in failures)
        raise RuntimeError(f"static template failed gates (should be impossible, I5): {detail}")
    return text, GateResult(passed=True, checks=checks, judge_scores=None)
