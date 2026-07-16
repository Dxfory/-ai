from backend.services.fenran_plan import build_fenran_teaching_plan


def test_default_plan_has_only_three_formal_stages():
    plan = build_fenran_teaching_plan(include_base_color=False)

    assert [stage.stage_id for stage in plan.stages] == [
        "stage_01_first_fenran",
        "stage_02_deepen_fenran",
        "stage_03_sap_green_glaze",
    ]
    assert plan.stages[0].pigments == ("花青", "淡墨")
    assert plan.stages[1].technique == "分染"
    assert plan.stages[1].pigments == ("花青",)
    assert "淡墨" not in plan.stages[1].pigments
    assert plan.stages[2].technique == "罩染"
    assert plan.stages[2].pigments == ("汁绿",)
    assert all("平染" not in stage.prompt and "局部提染" not in stage.prompt for stage in plan.stages)


def test_optional_base_color_is_first_and_is_not_default():
    plan = build_fenran_teaching_plan(include_base_color=True)

    assert plan.stages[0].stage_id == "stage_00_base_color"
    assert plan.stages[0].optional is True
    assert len(plan.stages) == 4


def test_each_stage_declares_previous_stage_dependency():
    plan = build_fenran_teaching_plan(include_base_color=True)

    assert plan.stages[0].depends_on is None
    assert plan.stages[1].depends_on == "stage_00_base_color"
    assert plan.stages[2].depends_on == "stage_01_first_fenran"
    assert plan.stages[3].depends_on == "stage_02_deepen_fenran"

