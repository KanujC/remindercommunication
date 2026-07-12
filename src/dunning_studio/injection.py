"""Post-generation fact injection. Facts never touch the LLM (I1); they are substituted here."""

import re

from dunning_studio.disclosures import get_disclosure
from dunning_studio.schemas import InvoiceFacts, format_amount, format_due_date

_TOKEN_RE = re.compile(r"\{\{[A-Z_]+\}\}")


def build_tokens(customer_name: str, merchant_name: str, facts: InvoiceFacts) -> dict[str, str]:
    return {
        "AMOUNT": format_amount(facts.amount_minor, facts.currency, facts.locale),
        "DUE_DATE": format_due_date(facts.due_date, facts.locale),
        "ACCOUNT_REF": facts.account_ref,
        "PAY_LINK": str(facts.pay_link),
        "DISCLOSURE": get_disclosure(facts.locale, facts.reminder_index),
        "CUSTOMER_NAME": customer_name,
        "MERCHANT_NAME": merchant_name,
    }


def inject(template_text: str, tokens: dict[str, str]) -> str:
    result = template_text
    for key, value in tokens.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


def unresolved_tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)
