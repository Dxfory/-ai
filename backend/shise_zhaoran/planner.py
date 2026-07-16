"""Object-level mineral-pigment plan generation."""

from .rules import (
    DEFAULT_RULES,
    OBJECT_LABELS,
    PIGMENTS,
    extract_rule_overrides,
    normalize_object_hint,
)
from .schemas import ObjectColorPlan


DEFAULT_OBJECTS = ["front_leaf", "back_leaf", "branch"]


def build_plan(
    *,
    subject_hints: list[str],
    user_rules: list[str],
    textbook_notes: str,
    reference_evidence: dict[str, tuple[str, str]] | None = None,
) -> list[ObjectColorPlan]:
    objects = _resolve_objects(subject_hints)
    textbook = extract_rule_overrides(textbook_notes, "textbook")
    user = extract_rule_overrides(user_rules + subject_hints, "user")
    reference_evidence = reference_evidence or {}
    plan: list[ObjectColorPlan] = []

    for object_type in objects:
        pigment_key, action = DEFAULT_RULES[object_type]
        source = "default"
        reason = "工笔花鸟基础定式"
        if object_type in reference_evidence:
            pigment_key, reason = reference_evidence[object_type]
            source = "reference"
        if object_type in textbook:
            override = textbook[object_type]
            pigment_key = override.pigment_key
            source = "textbook"
            reason = f"教材明确说明：{override.evidence}"
        if object_type in user:
            override = user[object_type]
            pigment_key = override.pigment_key
            source = "user"
            reason = f"用户明确指定：{override.evidence}"

        pigment = PIGMENTS[pigment_key]["name"]
        plan.append(
            ObjectColorPlan(
                object_type=object_type,
                object_label=OBJECT_LABELS[object_type],
                pigment=pigment,
                pigment_key=pigment_key,
                action=action,
                reason=reason,
                source=source,
                preserve=_preserve_rules(object_type),
            )
        )
    return plan


def _resolve_objects(subject_hints: list[str]) -> list[str]:
    resolved: list[str] = []
    for hint in subject_hints:
        object_type = normalize_object_hint(hint)
        if object_type and object_type not in resolved:
            resolved.append(object_type)
    return resolved or DEFAULT_OBJECTS.copy()


def _preserve_rules(object_type: str) -> list[str]:
    common = ["底层分染明暗", "墨线与对象边界"]
    if "leaf" in object_type:
        return common + ["叶脉", "虫孔", "叶缘水口"]
    if "insect" in object_type:
        return common + ["足与触角", "虫体分节"]
    if object_type == "bird":
        return common + ["羽毛边缘", "绒毛感", "体积转折"]
    if "fruit" in object_type:
        return common + ["果实缝隙", "成熟度色相"]
    return common
