from backend.shise_zhaoran.rules import DEFAULT_RULES, PIGMENTS, fixing_required, mineral_green_order


def test_medium_fixing_rules():
    assert fixing_required("silk") is True
    assert fixing_required("paper") is False


def test_mineral_green_lightness_order():
    order = mineral_green_order()
    ranks = [PIGMENTS[key]["lightness_rank"] for key in order]
    assert order == ("three_green", "four_green", "five_green")
    assert ranks == sorted(ranks)


def test_default_gongbi_mappings():
    assert DEFAULT_RULES["front_leaf"][0] == "three_green"
    assert DEFAULT_RULES["back_leaf"][0] == "four_green"
    assert DEFAULT_RULES["unripe_fruit"][0] == "four_green"
    assert DEFAULT_RULES["branch"][0] == "ochre_ink"
