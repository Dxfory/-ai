from backend.shise_zhaoran.planner import build_plan


def _by_type(plan):
    return {item.object_type: item for item in plan}


def test_plan_uses_defaults_without_overrides():
    plan = _by_type(
        build_plan(
            subject_hints=["正叶", "反叶", "未成熟果", "枝干"],
            user_rules=[],
            textbook_notes="",
        )
    )
    assert plan["front_leaf"].pigment == "三绿"
    assert plan["back_leaf"].pigment == "四绿"
    assert plan["unripe_fruit"].pigment == "四绿"
    assert plan["branch"].pigment == "赭墨"
    assert all(item.source == "default" for item in plan.values())


def test_textbook_rule_overrides_reference_and_default():
    plan = _by_type(
        build_plan(
            subject_hints=["正叶"],
            user_rules=[],
            textbook_notes="本课正叶罩五绿",
            reference_evidence={"front_leaf": ("four_green", "参考图证据")},
        )
    )
    assert plan["front_leaf"].pigment == "五绿"
    assert plan["front_leaf"].source == "textbook"


def test_user_rule_has_highest_priority():
    plan = _by_type(
        build_plan(
            subject_hints=["反叶"],
            user_rules=["反叶使用三绿"],
            textbook_notes="教材写明反叶罩五绿",
            reference_evidence={"back_leaf": ("four_green", "参考图证据")},
        )
    )
    assert plan["back_leaf"].pigment == "三绿"
    assert plan["back_leaf"].source == "user"
