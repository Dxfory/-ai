"""Reusable prompt construction for the Shise Zhaoran stage."""

from .schemas import ObjectColorPlan


def build_prompt(
    *,
    medium: str,
    plan: list[ObjectColorPlan],
    textbook_notes: str,
    teaching_goal: str,
) -> str:
    medium_rule = (
        "媒介为绢本，胶矾水固定已经完成并完全干燥。"
        if medium == "silk"
        else "媒介为纸本，胶矾水固定不是强制步骤。"
    )
    plan_lines = "\n".join(
        f"- {item.object_label}：{item.pigment}；{item.action}；依据：{item.reason}；必须保留：{'、'.join(item.preserve)}。"
        for item in plan
    )
    notes = textbook_notes.strip() or "无额外教材覆盖规则。"
    goal = teaching_goal.strip() or "完成传统工笔花鸟石色罩染阶段。"
    return f"""你正在继续绘制一张已经完成白描、分染和水色罩染的工笔花鸟画。
当前只执行独立的石色罩染阶段，不得重新生成白描，不得重做分染或水色罩染。
不得改变构图、对象造型、位置、比例和轮廓。必须保留底层分染明暗、水色综合色、墨线、叶脉、边线、虫孔、羽毛和细部结构。
石色必须薄而透明地罩上去，沉着、稳定、有矿物颜料完成阶段气质；不能厚涂糊死底层，不能做现代平面填色、绿色滤镜、喷点滤镜或整体重绘。

媒介规则：{medium_rule}
基础颜料关系：三绿较深，四绿比三绿浅，五绿比四绿浅；四绿仍可因底层与冷暖关系呈现偏冷、收敛和沉静。

对象级执行计划：
{plan_lines}

完成性补充：枝干结杈可稍浓赭墨提神；未成熟果可薄罩四绿；果实缝隙可赭墨压暗；鸟虫必须随体积推进；苔点必须以笔意点写。
教材说明：{notes}
教学目标：{goal}

输出仅为一张石色罩染完成图，保持输入图像尺寸和画面结构。"""
