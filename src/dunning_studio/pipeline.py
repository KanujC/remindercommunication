"""Pipeline orchestration. Side effects (model calls via llm.py, file writes) live here (I4/I6/12)."""

import json
import time
from pathlib import Path

from dunning_studio import fallback
from dunning_studio.fallback import gate_text, is_high_value
from dunning_studio.generator import GENERATOR_TEMPERATURE, generate
from dunning_studio.injection import build_tokens, inject
from dunning_studio.llm import LLMClient
from dunning_studio.schemas import CustomerRecord, InvoiceFacts, MerchantProfile, SendDecision
from dunning_studio.tone_policy import resolve_tone


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


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
    tokens = build_tokens(customer.customer_name, merchant.merchant_name, facts)

    raw = generate(
        client, customer.customer_name, merchant.merchant_name, facts, tone_spec,
        temperature=GENERATOR_TEMPERATURE,
    )
    text = inject(raw, tokens)
    gate_result, judge_calls = gate_text(
        text, facts, tone_spec, customer.customer_name, merchant.merchant_name, client, judge_enabled
    )
    model_calls = 1 + judge_calls
    fallback_steps_taken = 0
    source = "generated"

    if not gate_result.passed:
        failed_checks = [c for c in gate_result.checks if not c.passed]
        text, gate_result, calls = fallback.regenerate_step(
            client, customer.customer_name, merchant.merchant_name, facts, tone_spec,
            failed_checks, judge_enabled,
        )
        model_calls += calls
        fallback_steps_taken = 1
        source = "regenerated"

        if not gate_result.passed:
            static_ok = True
            try:
                static_text, static_gate = fallback.static_template_step(
                    tone_spec, facts, customer.customer_name, merchant.merchant_name
                )
            except RuntimeError:
                static_ok = False
                static_text, static_gate = text, gate_result

            if not static_ok or is_high_value(facts):
                fallback_steps_taken = 3
                source = "held"
                text, gate_result = static_text, static_gate
                if run_dir is not None:
                    _append_jsonl(
                        run_dir / "held.jsonl",
                        {
                            "case_id": case_id,
                            "reason": "static_template_failed" if not static_ok else "high_value",
                            "text": text,
                            "gate_result": gate_result.model_dump(),
                        },
                    )
            else:
                fallback_steps_taken = 2
                source = "static_template"
                text, gate_result = static_text, static_gate

    latency_ms = int((time.monotonic() - start) * 1000)
    decision = SendDecision(
        case_id=case_id,
        final_text=text,
        source=source,
        tone_spec=tone_spec,
        gate_result=gate_result,
        fallback_steps_taken=fallback_steps_taken,
        model_calls=model_calls,
        latency_ms=latency_ms,
    )

    if run_dir is not None:
        _append_jsonl(run_dir / "decisions.jsonl", decision.model_dump())

    return decision
