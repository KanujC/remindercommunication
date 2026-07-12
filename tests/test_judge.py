from dunning_studio.gates.judge import judge_checks, judge_passes, parse_judge_response


def test_parse_plain_json():
    raw = '{"register_match": 5, "firmness_accuracy": 4, "brand_voice": 5, "dignity": 5, "rationale": "ok"}'
    scores = parse_judge_response(raw)
    assert scores == {"register_match": 5, "firmness_accuracy": 4, "brand_voice": 5, "dignity": 5}


def test_parse_strips_code_fence():
    raw = '```json\n{"register_match": 3, "firmness_accuracy": 3, "brand_voice": 3, "dignity": 4, "rationale": "ok"}\n```'
    scores = parse_judge_response(raw)
    assert scores is not None
    assert scores["dignity"] == 4


def test_parse_failure_on_garbage():
    assert parse_judge_response("not json at all") is None


def test_parse_failure_on_missing_field():
    raw = '{"register_match": 5, "firmness_accuracy": 4, "dignity": 5}'
    assert parse_judge_response(raw) is None


def test_parse_failure_on_out_of_range_score():
    raw = '{"register_match": 9, "firmness_accuracy": 4, "brand_voice": 5, "dignity": 5}'
    assert parse_judge_response(raw) is None


def test_judge_passes_rule():
    assert judge_passes({"register_match": 3, "firmness_accuracy": 3, "brand_voice": 1, "dignity": 4})


def test_judge_fails_on_low_dignity():
    assert not judge_passes({"register_match": 5, "firmness_accuracy": 5, "brand_voice": 5, "dignity": 3})


def test_judge_fails_on_low_firmness_accuracy():
    assert not judge_passes({"register_match": 5, "firmness_accuracy": 2, "brand_voice": 5, "dignity": 5})


def test_judge_checks_all_pass():
    checks = judge_checks({"register_match": 5, "firmness_accuracy": 4, "brand_voice": 1, "dignity": 5})
    assert {c.check_id for c in checks} == {"J1", "J2", "J3", "J4"}
    assert all(c.passed for c in checks)  # brand_voice=1 is non-gating (J3), so still passes


def test_judge_checks_dignity_gates():
    checks = judge_checks({"register_match": 5, "firmness_accuracy": 5, "brand_voice": 5, "dignity": 3})
    j4 = next(c for c in checks if c.check_id == "J4")
    assert not j4.passed
    assert not all(c.passed for c in checks)


def test_judge_checks_parse_failure():
    checks = judge_checks(None)
    assert len(checks) == 1
    assert checks[0].check_id == "J1" and not checks[0].passed
