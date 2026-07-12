"""Pipeline orchestration. Side effects (model calls via llm.py, file writes) live here (I4/I6/12)."""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dunning_studio import fallback
from dunning_studio.fallback import gate_text, is_high_value
from dunning_studio.generator import GENERATOR_TEMPERATURE, generate
from dunning_studio.injection import build_tokens, inject
from dunning_studio.llm import LLMClient
from dunning_studio.schemas import (
    CustomerRecord, GateResult, InvoiceFacts, MerchantProfile, SendDecision, ToneSpec,
)
from dunning_studio.tone_policy import resolve_tone

Source = Literal["generated", "regenerated", "static_template", "held"]


@dataclass
class _Attempt:
    """Mutable state threaded through the fallback ladder before it becomes a SendDecision."""

    text: str
    gate_result: GateResult
    source: Source
    fallback_steps_taken: int
    model_calls: int
    held_reason: str | None = None


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _first_attempt(
    customer: CustomerRecord,
    merchant: MerchantProfile,
    facts: InvoiceFacts,
    tone_spec: ToneSpec,
    client: LLMClient,
    judge_enabled: bool,
) -> _Attempt:
    raw = generate(
        client, customer.customer_name, merchant.merchant_name, facts, tone_spec,
        temperature=GENERATOR_TEMPERATURE,
    )
    text = inject(raw, build_tokens(customer.customer_name, merchant.merchant_name, facts))
    gate_result, judge_calls = gate_text(
        text, facts, tone_spec, customer.customer_name, merchant.merchant_name, client, judge_enabled
    )
    return _Attempt(text, gate_result, "generated", 0, 1 + judge_calls)


def _walk_fallback_ladder(
    attempt: _Attempt,
    customer: CustomerRecord,
    merchant: MerchantProfile,
    facts: InvoiceFacts,
    tone_spec: ToneSpec,
    client: LLMClient,
    judge_enabled: bool,
) -> _Attempt:
    """Ladder per CLAUDE.md 8: regenerate -> static template -> hold. Mutates and returns `attempt`."""
    failed_checks = [c for c in attempt.gate_result.checks if not c.passed]
    text, gate_result, calls = fallback.regenerate_step(
        client, customer.customer_name, merchant.merchant_name, facts, tone_spec,
        failed_checks, judge_enabled,
    )
    attempt.text, attempt.gate_result = text, gate_result
    attempt.model_calls += calls
    attempt.fallback_steps_taken, attempt.source = 1, "regenerated"
    if gate_result.passed:
        return attempt

    return _hold_or_static(attempt, customer, merchant, facts, tone_spec)


def _hold_or_static(
    attempt: _Attempt,
    customer: CustomerRecord,
    merchant: MerchantProfile,
    facts: InvoiceFacts,
    tone_spec: ToneSpec,
) -> _Attempt:
    try:
        static_text, static_gate = fallback.static_template_step(
            tone_spec, facts, customer.customer_name, merchant.merchant_name
        )
    except RuntimeError:  # I5 breached for this cell: hold the failed regen draft for review
        attempt.fallback_steps_taken, attempt.source = 3, "held"
        attempt.held_reason = "static_template_failed"
        return attempt

    attempt.text, attempt.gate_result = static_text, static_gate
    if is_high_value(facts):
        attempt.fallback_steps_taken, attempt.source = 3, "held"
        attempt.held_reason = "high_value"
    else:
        attempt.fallback_steps_taken, attempt.source = 2, "static_template"
    return attempt


def run_case(
    case_id: str,
    customer: CustomerRecord,
    merchant: MerchantProfile,
    facts: InvoiceFacts,
    client: LLMClient,
    run_dir: Path | None = None,
    judge_enabled: bool = False,
) -> SendDecision:
    """Runs one case end to end. Never returns generator output without a GateResult (I4)."""
    start = time.monotonic()
    tone_spec = resolve_tone(customer, merchant, facts)

    attempt = _first_attempt(customer, merchant, facts, tone_spec, client, judge_enabled)
    if not attempt.gate_result.passed:
        attempt = _walk_fallback_ladder(
            attempt, customer, merchant, facts, tone_spec, client, judge_enabled
        )

    decision = SendDecision(
        case_id=case_id,
        final_text=attempt.text,
        source=attempt.source,
        tone_spec=tone_spec,
        gate_result=attempt.gate_result,
        fallback_steps_taken=attempt.fallback_steps_taken,
        model_calls=attempt.model_calls,
        latency_ms=int((time.monotonic() - start) * 1000),
    )

    if run_dir is not None:
        _persist(run_dir, decision, attempt.held_reason)
    return decision


def _persist(run_dir: Path, decision: SendDecision, held_reason: str | None) -> None:
    if decision.source == "held":
        _append_jsonl(
            run_dir / "held.jsonl",
            {
                "case_id": decision.case_id,
                "reason": held_reason,
                "text": decision.final_text,
                "gate_result": decision.gate_result.model_dump(),
            },
        )
    _append_jsonl(run_dir / "decisions.jsonl", decision.model_dump())
