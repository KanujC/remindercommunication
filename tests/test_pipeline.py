from datetime import date
from pathlib import Path

from dunning_studio.llm import MockLLMClient
from dunning_studio.pipeline import run_case
from dunning_studio.schemas import CustomerRecord, InvoiceFacts, MerchantProfile

_GOOD_TEXT = (
    "Hi Alex,\n\n"
    "We hope you're doing well! We wanted to check in because the invoice {{ACCOUNT_REF}} for "
    "{{AMOUNT}}, due on {{DUE_DATE}}, hasn't been settled yet. {{DISCLOSURE}} We'd really "
    "appreciate it if you could take care of it using the link below when you get a chance.\n\n"
    "{{PAY_LINK}}\n\n"
    "Thanks so much,\nNordwind Fitness"
)

_BAD_TEXT = "this response mentions a lawsuit and never resolves any tokens"


def _customer(**overrides) -> CustomerRecord:
    base = dict(
        customer_id="c1", customer_name="Alex Doe", on_time_rate=0.6, prior_defaults=2,
        days_past_due_avg=14.0, last_payment_days_ago=40, account_age_days=365,
    )
    base.update(overrides)
    return CustomerRecord(**base)


def _merchant(**overrides) -> MerchantProfile:
    base = dict(merchant_id="m1", merchant_name="Nordwind Fitness", voice="friendly")
    base.update(overrides)
    return MerchantProfile(**base)


def _facts(**overrides) -> InvoiceFacts:
    base = dict(
        amount_minor=4900, currency="EUR", due_date=date(2026, 6, 15), account_ref="INV-1",
        pay_link="https://pay.example.com/inv-1", locale="en-GB", channel="email", reminder_index=2,
    )
    base.update(overrides)
    return InvoiceFacts(**base)


def test_source_generated_on_first_pass():
    client = MockLLMClient(responses=[_GOOD_TEXT])
    decision = run_case("t1", _customer(), _merchant(), _facts(), client)
    assert decision.source == "generated"
    assert decision.fallback_steps_taken == 0
    assert decision.gate_result.passed


def test_source_regenerated_when_second_attempt_passes():
    client = MockLLMClient(responses=[_BAD_TEXT, _GOOD_TEXT])
    decision = run_case("t2", _customer(), _merchant(), _facts(), client)
    assert decision.source == "regenerated"
    assert decision.fallback_steps_taken == 1


def test_source_static_template_when_both_attempts_fail():
    client = MockLLMClient(responses=[_BAD_TEXT, _BAD_TEXT])
    decision = run_case("t3", _customer(), _merchant(), _facts(), client)
    assert decision.source == "static_template"
    assert decision.fallback_steps_taken == 2
    assert decision.gate_result.passed


def test_source_held_when_high_value_and_both_attempts_fail():
    client = MockLLMClient(responses=[_BAD_TEXT, _BAD_TEXT])
    high_value_facts = _facts(amount_minor=100_000)
    decision = run_case("t4", _customer(), _merchant(), high_value_facts, client)
    assert decision.source == "held"
    assert decision.fallback_steps_taken == 3


def test_held_writes_jsonl(tmp_path: Path):
    client = MockLLMClient(responses=[_BAD_TEXT, _BAD_TEXT])
    high_value_facts = _facts(amount_minor=100_000)
    run_case("t5", _customer(), _merchant(), high_value_facts, client, run_dir=tmp_path)
    assert (tmp_path / "held.jsonl").exists()
    assert (tmp_path / "decisions.jsonl").exists()


def test_i4_every_decision_has_a_gate_result():
    client = MockLLMClient(responses=[_GOOD_TEXT])
    decision = run_case("t6", _customer(), _merchant(), _facts(), client)
    assert decision.gate_result is not None
    assert len(decision.gate_result.checks) >= 10


def _judge_aware_fn(good_scores: bool):
    judge_json = (
        '{"register_match": 5, "firmness_accuracy": 4, "brand_voice": 5, "dignity": %d, "rationale": "ok"}'
        % (5 if good_scores else 1)
    )

    def fn(system: str, user: str, temperature: float) -> str:
        return judge_json if "reviewer" in system else _GOOD_TEXT

    return fn


def test_judge_enabled_appends_j_checks_and_passes():
    client = MockLLMClient(fn=_judge_aware_fn(good_scores=True))
    decision = run_case("t7", _customer(), _merchant(), _facts(), client, judge_enabled=True)
    assert decision.source == "generated"
    assert decision.gate_result.passed
    j_ids = {c.check_id for c in decision.gate_result.checks if c.check_id.startswith("J")}
    assert j_ids == {"J1", "J2", "J3", "J4"}
    assert decision.gate_result.judge_scores is not None
    assert decision.model_calls == 2  # one generate + one judge


def test_judge_low_dignity_routes_to_fallback():
    client = MockLLMClient(fn=_judge_aware_fn(good_scores=False))
    decision = run_case("t8", _customer(), _merchant(), _facts(), client, judge_enabled=True)
    assert decision.source != "generated"  # J4 (dignity) failed, so it left the happy path
