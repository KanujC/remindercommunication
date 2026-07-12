"""LLM-as-judge tone scoring. Judge scores tone only; safety is carried by A1..A10 (I6).
See CLAUDE.md section 7.2. Parsing is defensive: any failure counts as judge-fail."""

import json
import re
from pathlib import Path

from dunning_studio.llm import LLMClient
from dunning_studio.schemas import ToneSpec

_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"
_JUDGE_PROMPT_PATH = _PROMPTS_DIR / "judge_v1.md"

JUDGE_DIMENSIONS = ("register_match", "firmness_accuracy", "brand_voice", "dignity")
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _load_judge_prompt() -> str:
    return _JUDGE_PROMPT_PATH.read_text(encoding="utf-8")


def build_judge_user_message(final_text: str, tone_spec: ToneSpec) -> str:
    return (
        "<message>\n"
        f"{final_text}\n"
        "</message>\n\n"
        "<tone_spec>\n"
        f"segment: {tone_spec.segment}\n"
        f"archetype: {tone_spec.archetype}\n"
        f"firmness: {tone_spec.firmness}\n"
        f"register_notes: {tone_spec.register_notes}\n"
        "</tone_spec>\n\n"
        "Score this message now."
    )


def parse_judge_response(raw: str) -> dict[str, int] | None:
    """Returns None (judge-fail) on any parse error, missing field, or out-of-range score."""
    stripped = _CODE_FENCE_RE.sub("", raw.strip()).strip()
    try:
        data = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    scores: dict[str, int] = {}
    for dim in JUDGE_DIMENSIONS:
        value = data.get(dim)
        if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= 5):
            return None
        scores[dim] = value
    return scores


def judge_passes(scores: dict[str, int]) -> bool:
    return scores["dignity"] >= 4 and scores["firmness_accuracy"] >= 3 and scores["register_match"] >= 3


def run_judge(client: LLMClient, final_text: str, tone_spec: ToneSpec) -> dict[str, int] | None:
    system = _load_judge_prompt()
    user = build_judge_user_message(final_text, tone_spec)
    raw = client.complete(system=system, user=user, temperature=0.0)
    return parse_judge_response(raw)
