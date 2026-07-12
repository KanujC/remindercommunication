"""Reminder generation. Tone only — facts are opaque tokens (I1). See CLAUDE.md section 6."""

from pathlib import Path

from dunning_studio.llm import LLMClient
from dunning_studio.schemas import GateCheck, InvoiceFacts, ToneSpec

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_GENERATOR_PROMPT_PATH = _PROMPTS_DIR / "generator_v1.md"

GENERATOR_TEMPERATURE = 0.7
REGENERATE_TEMPERATURE = 0.0


def _load_generator_prompt() -> str:
    return _GENERATOR_PROMPT_PATH.read_text(encoding="utf-8")


def build_system_prompt(tone_spec: ToneSpec, constraint_block: str | None = None) -> str:
    base = _load_generator_prompt()
    tone_section = (
        "\n\n## This case's ToneSpec\n\n"
        f"- segment: {tone_spec.segment}\n"
        f"- archetype: {tone_spec.archetype}\n"
        f"- firmness: {tone_spec.firmness} (1=light nudge .. 5=final notice)\n"
        f"- register_notes: {tone_spec.register_notes}\n"
    )
    parts = [base, tone_section]
    if constraint_block:
        parts.append(constraint_block)
    return "".join(parts)


def build_user_message(
    customer_name: str, merchant_name: str, channel: str, reminder_index: int
) -> str:
    return (
        "<data>\n"
        f"customer_name: {customer_name}\n"
        f"merchant_name: {merchant_name}\n"
        f"channel: {channel}\n"
        f"reminder_index: {reminder_index}\n"
        "</data>\n"
        "Write the reminder now. Use {{AMOUNT}}, {{DUE_DATE}}, {{PAY_LINK}}, "
        "{{ACCOUNT_REF}}, {{DISCLOSURE}} exactly as given."
    )


def build_constraint_block(failed_checks: list[GateCheck]) -> str:
    lines = ["\n\n## Fix these specific failures from the previous attempt\n"]
    for check in failed_checks:
        lines.append(f"- {check.check_id}: {check.detail}\n")
    return "".join(lines)


def generate(
    client: LLMClient,
    customer_name: str,
    merchant_name: str,
    facts: InvoiceFacts,
    tone_spec: ToneSpec,
    temperature: float = GENERATOR_TEMPERATURE,
    failed_checks: list[GateCheck] | None = None,
) -> str:
    constraint_block = build_constraint_block(failed_checks) if failed_checks else None
    system = build_system_prompt(tone_spec, constraint_block)
    user = build_user_message(customer_name, merchant_name, facts.channel, facts.reminder_index)
    return client.complete(system=system, user=user, temperature=temperature)
