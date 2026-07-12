"""`dunning run <case_id>` and `dunning demo`. Shows the full gate trace."""

import time
from datetime import date
from pathlib import Path

import click

from dunning_studio.llm import AnthropicLLMClient, LLMClient, MockLLMClient
from dunning_studio.pipeline import run_case
from dunning_studio.schemas import CustomerRecord, InvoiceFacts, MerchantProfile, SendDecision
from dunning_studio.template_loader import validate_all_templates

_DEMO_CUSTOMER = CustomerRecord(
    customer_id="cust-demo",
    customer_name="Alex Doe",
    on_time_rate=0.6,
    prior_defaults=2,
    days_past_due_avg=14.0,
    last_payment_days_ago=40,
    account_age_days=365,
)
_DEMO_MERCHANT = MerchantProfile(
    merchant_id="merch-demo", merchant_name="Nordwind Fitness", voice="friendly"
)
_DEMO_FACTS = InvoiceFacts(
    amount_minor=4900,
    currency="EUR",
    due_date=date(2026, 6, 15),
    account_ref="INV-2026-0042",
    pay_link="https://pay.example.com/inv-2026-0042",
    locale="en-GB",
    channel="email",
    reminder_index=2,
)

_DEMO_RESPONSE = (
    "Hi Alex,\n\n"
    "We hope you're doing well! We wanted to check in because the invoice {{ACCOUNT_REF}} for "
    "{{AMOUNT}}, due on {{DUE_DATE}}, hasn't been settled yet. {{DISCLOSURE}} We'd really "
    "appreciate it if you could take care of it using the link below when you get a chance.\n\n"
    "{{PAY_LINK}}\n\n"
    "Thanks so much,\nNordwind Fitness"
)


def _print_decision(decision: SendDecision) -> None:
    click.echo(click.style("ToneSpec", bold=True))
    click.echo(f"  segment={decision.tone_spec.segment} archetype={decision.tone_spec.archetype} "
               f"firmness={decision.tone_spec.firmness}")
    click.echo(f"  register_notes: {decision.tone_spec.register_notes}")
    click.echo()
    click.echo(click.style("Gate checks", bold=True))
    for check in decision.gate_result.checks:
        mark = "PASS" if check.passed else "FAIL"
        click.echo(f"  [{mark}] {check.check_id}: {check.detail}")
    click.echo()
    click.echo(click.style("Fallback", bold=True))
    click.echo(f"  source={decision.source} fallback_steps_taken={decision.fallback_steps_taken} "
               f"model_calls={decision.model_calls} latency_ms={decision.latency_ms}")
    click.echo()
    click.echo(click.style("Final text", bold=True))
    click.echo(decision.final_text)


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.option("--live", is_flag=True, help="Use the real Anthropic API instead of the mock client.")
@click.option("--judge/--no-judge", default=False, help="Run the tone judge gate.")
def demo(live: bool, judge: bool) -> None:
    """Run one synthetic case end to end and print the full trace."""
    validate_all_templates()
    client: LLMClient
    if live:
        client = AnthropicLLMClient()
    else:
        client = MockLLMClient(responses=[_DEMO_RESPONSE])
    run_dir = Path("runs") / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    decision = run_case(
        "demo-case", _DEMO_CUSTOMER, _DEMO_MERCHANT, _DEMO_FACTS, client,
        run_dir=run_dir, judge_enabled=judge,
    )
    _print_decision(decision)


@cli.command()
@click.argument("case_id")
@click.option("--golden-set", default="eval/golden_set.csv", help="CSV to load the case from.")
@click.option("--live", is_flag=True, help="Use the real Anthropic API instead of the mock client.")
@click.option("--judge/--no-judge", default=False, help="Run the tone judge gate.")
def run(case_id: str, golden_set: str, live: bool, judge: bool) -> None:
    """Run a single case from the golden set CSV by case_id."""
    from dunning_studio.eval_loader import load_case

    validate_all_templates()
    customer, merchant, facts = load_case(Path(golden_set), case_id)
    client: LLMClient = AnthropicLLMClient() if live else MockLLMClient(responses=[_DEMO_RESPONSE])
    run_dir = Path("runs") / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    decision = run_case(case_id, customer, merchant, facts, client, run_dir=run_dir, judge_enabled=judge)
    _print_decision(decision)


if __name__ == "__main__":
    cli()
