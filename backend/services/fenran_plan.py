"""Versioned Fenran teaching stages and prompts."""

from __future__ import annotations

from dataclasses import asdict, dataclass


TEACHING_PLAN_VERSION = "fenran-teaching-plan-v2"
PROMPT_VERSION = "fenran-stage-prompts-v2"

COMMON_PROMPT = """你是一位工笔花鸟画分染教学老师。
本次只生成一张完整的单幅绘画阶段图。
禁止制作教学海报。禁止生成文字、标题、编号、色卡、边框、多面板、第二幅图或局部放大图。
必须严格保持输入白描中的画布比例、主体数量、主体位置、主体大小、花瓣与叶片轮廓、叶脉关系、枝蔓连接、瓜果结构、昆虫姿态、牛筋草位置和留白关系。
禁止新增、删除、移动、缩放、旋转或裁切对象，禁止改变枝叶连接、昆虫姿态和整体构图。
背景保持原始纸色或纯净纸白，颜色不得越过主体结构边界。
第一张输入图是必须继续编辑的当前完整阶段；后续参考依次为原画和已审批白描。
"""


@dataclass(frozen=True)
class FenranStagePlan:
    stage_id: str
    title: str
    technique: str
    pigments: tuple[str, ...]
    depends_on: str | None
    optional: bool
    prompt: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["pigments"] = list(self.pigments)
        return payload


@dataclass(frozen=True)
class FenranTeachingPlan:
    version: str
    include_base_color: bool
    stages: tuple[FenranStagePlan, ...]

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "include_base_color": self.include_base_color,
            "stages": [stage.to_dict() for stage in self.stages],
        }


def _stage_prompt(instruction: str) -> str:
    return f"{COMMON_PROMPT}\n{instruction.strip()}\n只输出一张完整全图。"


def build_fenran_teaching_plan(*, include_base_color: bool = False) -> FenranTeachingPlan:
    stages: list[FenranStagePlan] = []
    first_dependency = None
    if include_base_color:
        stages.append(FenranStagePlan(
            stage_id="stage_00_base_color",
            title="制作底色",
            technique="底色",
            pigments=(),
            depends_on=None,
            optional=True,
            prompt=_stage_prompt("""
当前步骤：制作底色。根据原画可见色，在完整白描构图上建立很淡、很薄、透明的基础底色。
保留纸白、亮部和全部线条结构，不改变对象位置和轮廓。
"""),
        ))
        first_dependency = "stage_00_base_color"

    stages.extend((
        FenranStagePlan(
            stage_id="stage_01_first_fenran",
            title="第一遍分染",
            technique="分染",
            pigments=("花青", "淡墨"),
            depends_on=first_dependency,
            optional=False,
            prompt=_stage_prompt("""
当前步骤：第一遍分染。在当前完整构图基础上，使用花青加淡墨建立第一层基本明暗。
正叶、瓜果、牛筋草及需要建立明暗的相应对象，按叶脉、转折、遮挡、凹凸和结构做渐变。
颜色必须浅、薄、透；保留亮部、高光和纸白，不要一次染得过深，不要形成均匀色块。
不得改变任何线条结构、对象位置和整体构图。
"""),
        ),
        FenranStagePlan(
            stage_id="stage_02_deepen_fenran",
            title="加深分染",
            technique="分染",
            pigments=("花青",),
            depends_on="stage_01_first_fenran",
            optional=False,
            prompt=_stage_prompt("""
当前步骤：加深分染。必须在上一阶段结果上继续，禁止重新绘制或替换上一阶段。
本阶段只使用花青，不加入其他墨色。正叶、瓜果及相应对象继续加深叶脉附近、内部转折、遮挡、重叠、瓜果凹陷和结构暗部。
保留第一阶段的浅层颜色、亮部、高光和透明层次，不要无差别压暗。
不得改变任何轮廓和构图。
"""),
        ),
        FenranStagePlan(
            stage_id="stage_03_sap_green_glaze",
            title="正叶整体罩染汁绿",
            technique="罩染",
            pigments=("汁绿",),
            depends_on="stage_02_deepen_fenran",
            optional=False,
            prompt=_stage_prompt("""
当前步骤：正叶整体罩染汁绿。必须在上一阶段分染结果上继续，禁止重新绘制或替换上一阶段。
在已完成花青分染的正叶上整体薄罩一层透明汁绿，用来统一综合色相。
颜色必须薄、透、均匀，并保留下层明暗、叶脉、亮部和结构转折；不得形成没有深浅的平绿色块，不得压暗其他对象。
不得改变任何轮廓和构图。
"""),
        ),
    ))
    return FenranTeachingPlan(TEACHING_PLAN_VERSION, include_base_color, tuple(stages))

