"""LLM-as-judge tone scoring. Judge scores tone only; safety is carried by A1..A10 (I6).
See CLAUDE.md section 7.2. Parsing is defensive: any failure counts as judge-fail."""

import json
import re
from pathlib import Path

from dunning_studio.llm import LLMClient
from dunning_studio.schemas import GateCheck, ToneSpec

_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"
_JUDGE_PROMPT_PATH = _PROMPTS_DIR / "judge_v1.md"

JUDGE_DIMENSIONS = ("register_match", "firmness_accuracy", "brand_voice", "dignity")
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

# Rubric v1 gating thresholds (CLAUDE.md 7.2). brand_voice is reported but not gating in v1.
_GATING_THRESHOLDS = {"register_match": 3, "firmness_accuracy": 3, "dignity": 4}
# Report ids per dimension (CLAUDE.md 9.3 references the per-check table as "A1..A10, J*").
_JUDGE_CHECK_IDS = {
    "register_match": "J1", "firmness_accuracy": "J2", "brand_voice": "J3", "dignity": "J4",
}


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
    return all(scores[dim] >= threshold for dim, threshold in _GATING_THRESHOLDS.items())


def judge_checks(scores: dict[str, int] | None) -> list[GateCheck]:
    """Turn judge scores into one GateCheck per rubric dimension (J1..J4). A parse failure
    (scores is None) is itself a single failing judge check, per CLAUDE.md 7.2."""
    if scores is None:
        return [GateCheck(check_id="J1", passed=False, detail="judge parse failure")]
    checks = []
    for dim in JUDGE_DIMENSIONS:
        threshold = _GATING_THRESHOLDS.get(dim)
        if threshold is None:
            detail, passed = f"{dim}={scores[dim]} (non-gating)", True
        else:
            detail, passed = f"{dim}={scores[dim]} (need >= {threshold})", scores[dim] >= threshold
        checks.append(GateCheck(check_id=_JUDGE_CHECK_IDS[dim], passed=passed, detail=detail))
    return checks


def run_judge(client: LLMClient, final_text: str, tone_spec: ToneSpec) -> dict[str, int] | None:
    system = _load_judge_prompt()
    user = build_judge_user_message(final_text, tone_spec)
    raw = client.complete(system=system, user=user, temperature=0.0)
    return parse_judge_response(raw)
