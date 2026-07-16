"""Traditional Gongbi mineral-pigment rules and precedence helpers."""

import re
from dataclasses import dataclass


PIGMENTS = {
    "three_green": {"name": "三绿", "lightness_rank": 3},
    "four_green": {"name": "四绿", "lightness_rank": 4},
    "five_green": {"name": "五绿", "lightness_rank": 5},
    "ochre_ink": {"name": "赭墨", "lightness_rank": 2},
    "ochre_yellow": {"name": "赭石加藤黄", "lightness_rank": 3},
    "indigo_ink": {"name": "花青加墨", "lightness_rank": 1},
    "intrinsic_color": {"name": "延续固有色", "lightness_rank": 0},
    "composite_bird": {"name": "赭墨、四绿与综合色", "lightness_rank": 3},
    "moss_dot": {"name": "综合色点写", "lightness_rank": 2},
}

OBJECT_LABELS = {
    "front_leaf": "正叶",
    "back_leaf": "反叶",
    "young_leaf": "嫩叶",
    "ripe_fruit": "成熟果",
    "unripe_fruit": "未成熟果",
    "bird": "鸟",
    "green_insect": "绿色虫体",
    "brown_insect": "褐色虫体",
    "branch": "枝干",
    "vine": "藤蔓",
    "grass": "牛筋草",
    "moss": "苔点",
}

OBJECT_ALIASES = {
    "front_leaf": ("front_leaf", "front leaf", "正叶", "叶正面"),
    "back_leaf": ("back_leaf", "back leaf", "反叶", "叶背"),
    "young_leaf": ("young_leaf", "young leaf", "嫩叶"),
    "ripe_fruit": ("ripe_fruit", "ripe fruit", "成熟果", "熟果"),
    "unripe_fruit": ("unripe_fruit", "unripe fruit", "未成熟果", "未熟果", "青果"),
    "bird": ("bird", "鸟"),
    "green_insect": ("green_insect", "green insect", "绿色虫", "绿虫"),
    "brown_insect": ("brown_insect", "brown insect", "褐色虫", "褐虫"),
    "branch": ("branch", "stem", "枝干", "枝", "干"),
    "vine": ("vine", "藤蔓", "藤"),
    "grass": ("grass", "牛筋草", "草"),
    "moss": ("moss", "苔点", "苔"),
}

PIGMENT_ALIASES = {
    "three_green": ("three_green", "三绿"),
    "four_green": ("four_green", "四绿"),
    "five_green": ("five_green", "五绿"),
    "ochre_ink": ("ochre_ink", "赭墨"),
    "ochre_yellow": ("ochre_yellow", "赭石加藤黄", "赭石+藤黄"),
    "indigo_ink": ("indigo_ink", "花青加墨", "花青+墨"),
    "intrinsic_color": ("intrinsic_color", "固有色"),
}

DEFAULT_RULES = {
    "front_leaf": ("three_green", "罩染，正面保持较稳重的石绿色层"),
    "back_leaf": ("four_green", "罩染，保持反叶较浅且偏冷收敛"),
    "young_leaf": ("four_green", "薄罩并向更浅层过渡"),
    "ripe_fruit": ("intrinsic_color", "延续成熟果固有色，不机械加绿"),
    "unripe_fruit": ("four_green", "在未成熟部位薄罩四绿"),
    "bird": ("composite_bird", "随体积薄罩，保留羽毛和绒毛结构"),
    "green_insect": ("four_green", "沿虫体结构薄罩，保留足与触角"),
    "brown_insect": ("ochre_yellow", "薄罩后以赭墨点斑"),
    "branch": ("ochre_ink", "继续皴染提染，结杈处稍浓提神"),
    "vine": ("four_green", "按藤蔓转折薄罩或用综合色统一"),
    "grass": ("indigo_ink", "沿草叶结构罩染，不作平涂"),
    "moss": ("moss_dot", "以笔意点写，不生成喷点滤镜"),
}


@dataclass(frozen=True)
class RuleOverride:
    object_type: str
    pigment_key: str
    source: str
    evidence: str


def mineral_green_order() -> tuple[str, str, str]:
    return ("three_green", "four_green", "five_green")


def fixing_required(medium: str) -> bool:
    return medium == "silk"


def normalize_object_hint(hint: str) -> str | None:
    value = hint.strip().lower()
    matches = [
        (len(alias), object_type)
        for object_type, aliases in OBJECT_ALIASES.items()
        for alias in aliases
        if alias.lower() in value
    ]
    return max(matches)[1] if matches else None


def extract_rule_overrides(lines: list[str] | str, source: str) -> dict[str, RuleOverride]:
    text_items = [lines] if isinstance(lines, str) else lines
    overrides: dict[str, RuleOverride] = {}
    for item in text_items:
        for segment in re.split(r"[，。；;\n]+", item):
            lowered = segment.lower()
            object_type = normalize_object_hint(segment)
            if not object_type:
                continue
            for pigment_key, aliases in PIGMENT_ALIASES.items():
                if any(alias.lower() in lowered for alias in aliases):
                    overrides[object_type] = RuleOverride(object_type, pigment_key, source, segment.strip())
                    break
    return overrides
