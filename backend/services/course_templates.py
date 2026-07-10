"""课程模板引擎 — 按画种+画法生成完整教学步骤

严格遵循方案修改版：工笔/写意 分轨，步骤不可打乱。
"""

from typing import List, Dict, Any
from shared.types import MaterialItem


# ============ 画材定义 ============

MATERIALS = {
    "gongbi_brush_line": MaterialItem(
        category="brush", name="兼毫勾线笔", description="中锋勾线，线条匀净",
    ),
    "xieyi_brush_big": MaterialItem(
        category="brush", name="羊毫大笔",
        description="铺色用，含水量大，一笔见浓淡",
    ),
    "xieyi_brush_med": MaterialItem(
        category="brush", name="兼毫中笔",
        description="造型用，笔触肯定",
    ),
    "landscape_brush_wolf": MaterialItem(
        category="brush", name="狼毫山水笔",
        description="硬毫弹性好，用于皴擦；笔中水分要少",
    ),
    "landscape_brush_sheep": MaterialItem(
        category="brush", name="羊毫或兼毫笔",
        description="软毫含水量大，用于染色",
    ),
    "paper_shuxuan": MaterialItem(category="paper", name="熟宣/绢", description="不洇墨，适合工笔"),
    "paper_shengxuan": MaterialItem(category="paper", name="生宣", description="洇墨，适合写意"),
    "paper_bansheng": MaterialItem(category="paper", name="半生熟宣", description="水墨控制适中"),
    "ink_youyan": MaterialItem(category="ink", name="油烟墨", description="工笔勾线用，墨色光亮"),
    "ink_songyan": MaterialItem(category="ink", name="松烟墨", description="山水皴擦用，墨色沉稳"),
    "color_xieyi": MaterialItem(category="color", name="国画颜料", description="赭石、花青、藤黄等"),
}

# ============ 步骤模板 ============

STEPS_GONGBI_FLOWER_BIRD = [
    {
        "title": "构图定位",
        "instruction": "用炭条轻定位主体位置和比例关系。注意主体不宜居中，遵循「三七停」构图法则。炭条要轻，勿重压纸面。",
        "materials": [MATERIALS["paper_shuxuan"], MATERIALS["ink_youyan"]],
        "checklist": ["主体位置是否偏离中心？", "比例是否与原作一致？", "炭条痕迹是否轻到可擦除？"],
        "common_mistakes": ["主体偏移中心", "比例失真", "构图太满或太空"],
    },
    {
        "title": "勾线",
        "instruction": "用兼毫勾线笔中锋行笔，沿炭条定位勾勒轮廓。线条要匀净、起收笔含蓄，注意花瓣的转折和叶片的主脉走向。中锋行笔即笔杆垂直纸面，笔尖始终在线条中央。",
        "materials": [MATERIALS["gongbi_brush_line"], MATERIALS["paper_shuxuan"], MATERIALS["ink_youyan"]],
        "checklist": ["线条是否均匀？", "起笔收笔是否含蓄？", "是否中锋行笔？"],
        "common_mistakes": ["线条粗细不匀", "断线或接头明显", "偏锋导致线条单薄"],
    },
    {
        "title": "复勾调整",
        "instruction": "用勾线笔重新提勾关键轮廓线，只勾主结构线，不求全勾。复勾要轻，与原线重合而非覆盖。检查整体画面，调整疏密关系和局部细节。",
        "materials": [MATERIALS["gongbi_brush_line"], MATERIALS["paper_shuxuan"], MATERIALS["ink_youyan"]],
        "checklist": ["是否只勾了主结构线？", "复勾是否与原线重合？", "整体疏密是否协调？"],
        "common_mistakes": ["复勾过重破坏层次", "全勾导致画面僵硬", "忽略背景留白"],
    },
]

STEPS_XIEYI_FLOWER_BIRD = [
    {
        "title": "构图定位",
        "instruction": "心中有全局再落笔。确定花头、叶片、枝干的位置和疏密关系。写意画讲究「意在笔先」，落笔前就要想好墨色的浓淡干湿分布。",
        "materials": [MATERIALS["paper_shengxuan"]],
        "checklist": ["疏密关系是否合理？", "主次是否分明？", "心中是否有全局？"],
        "common_mistakes": ["构图太满或太空", "心中无全局就动笔", "主次不分"],
    },
    {
        "title": "调色",
        "instruction": "在调色盘中备好所需颜色。写意画的颜色要饱满而有变化，一笔之中含浓淡。调色不要太稀，否则没有笔触变化。花头色要有浓淡渐变，叶色要有墨色变化。",
        "materials": [MATERIALS["xieyi_brush_big"], MATERIALS["paper_shengxuan"], MATERIALS["color_xieyi"]],
        "checklist": ["颜色是否饱满？", "一笔中是否有浓淡变化？", "调色是否太稀？"],
        "common_mistakes": ["调色过稀", "颜色单一无变化", "忘记留出高光"],
    },
    {
        "title": "画花叶鸟主体",
        "instruction": "羊毫大笔铺色，兼毫中笔造型。一笔见浓淡，笔触要肯定，不要反复涂抹。画花要从花心向外，画叶要一笔成形，画鸟要抓住动态。",
        "materials": [MATERIALS["xieyi_brush_big"], MATERIALS["xieyi_brush_med"], MATERIALS["paper_shengxuan"], MATERIALS["color_xieyi"]],
        "checklist": ["笔触是否肯定？", "是否一笔见浓淡？", "是否避免反复涂抹？"],
        "common_mistakes": ["反复涂抹", "笔触琐碎", "不敢下笔"],
    },
    {
        "title": "穿枝干",
        "instruction": "用兼毫笔穿插枝干连接花叶。枝干要有穿插呼应，注意主枝与分枝的粗细变化和转折角度。枝干要用较干的笔触，与花叶的湿润形成对比。",
        "materials": [MATERIALS["xieyi_brush_med"], MATERIALS["paper_shengxuan"], MATERIALS["ink_songyan"]],
        "checklist": ["枝干是否与花叶呼应？", "主次枝干粗细是否有变化？", "枝干墨色是否较干？"],
        "common_mistakes": ["枝干与花叶脱节", "枝干粗细无变化", "枝干墨色过湿"],
    },
    {
        "title": "调整画面",
        "instruction": "审视整体画面的黑白灰关系和疏密节奏。少加多减，宁简勿繁。在关键处补几笔提神，切忌越改越乱。写意画的最高境界是「恰到好处即停笔」。",
        "materials": [MATERIALS["xieyi_brush_med"], MATERIALS["paper_shengxuan"]],
        "checklist": ["黑白灰关系是否和谐？", "疏密节奏是否舒服？", "是否做到「恰到好处即停笔」？"],
        "common_mistakes": ["越改越乱", "画面过满", "缺乏留白"],
    },
]

STEPS_XIEYI_LANDSCAPE = [
    {
        "title": "构图定位",
        "instruction": "确定山体、树木、水流、房屋的大致位置。近中远景三层分置，主山放在黄金分割点附近。注意「高远、深远、平远」三远法的运用。",
        "materials": [MATERIALS["paper_shengxuan"]],
        "checklist": ["近中远景是否三层分置？", "主山位置是否在黄金分割点？", "三远法是否运用到位？"],
        "common_mistakes": ["主次不分", "构图平板", "缺乏空间层次"],
    },
    {
        "title": "勾勒轮廓",
        "instruction": "用狼毫山水笔中锋勾勒山体和树的轮廓。中锋行笔即笔杆垂直纸面，笔尖始终在线条中央。笔中水分要少，线条要肯定有力度。记住：用笔肯定、不宜太快。",
        "materials": [MATERIALS["landscape_brush_wolf"], MATERIALS["paper_shengxuan"], MATERIALS["ink_songyan"]],
        "checklist": ["是否中锋行笔？", "线条是否肯定有力？", "笔中水分是否控制得当？"],
        "common_mistakes": ["用笔虚浮", "不敢下笔", "行笔太快导致线条草率"],
    },
    {
        "title": "淡墨皴擦逐次加重",
        "instruction": "从淡墨开始皴擦，逐步加深层次。笔中水分要少，行笔有速度时自然出现飞白——这正是正确的皴法效果，不要刻意追求也不要刻意回避。蘸墨后在废纸上吸去多余水分，笔尖微微发涩才是正确状态。每一遍皴擦干透后再加下一遍。",
        "materials": [MATERIALS["landscape_brush_wolf"], MATERIALS["paper_shengxuan"], MATERIALS["ink_songyan"]],
        "checklist": ["笔中水分是否够少？", "是否从淡墨开始逐次加重？", "是否每遍干透后再加？", "自然出现的飞白是否保留？"],
        "common_mistakes": ["水分过多导致墨色洇成团", "不敢下笔反复描摹", "急于求成一次画太重", "把飞白当错误反复回填"],
    },
    {
        "title": "画树/房屋",
        "instruction": "同时勾勒树木和房屋，先勾轮廓再逐层加重渲染层次。树的造型要与山体呼应，房屋的朝向要与山势协调。同样用中锋行笔，逐层从淡到浓。",
        "materials": [MATERIALS["landscape_brush_wolf"], MATERIALS["paper_shengxuan"], MATERIALS["ink_songyan"]],
        "checklist": ["树与山体是否呼应？", "是否从淡到浓逐层加重？", "房屋与山势是否协调？"],
        "common_mistakes": ["树石各自孤立", "树与山比例失调", "房屋朝向前后矛盾"],
    },
    {
        "title": "点苔点",
        "instruction": "在山体和树木的关键转折处点苔增加层次感和生命力。苔点要疏密有致，三五成群。笔触要果断干脆，用笔尖快速点下提起。",
        "materials": [MATERIALS["landscape_brush_wolf"], MATERIALS["paper_shengxuan"], MATERIALS["ink_songyan"]],
        "checklist": ["苔点疏密是否有致？", "苔点位置是否在关键转折处？", "笔触是否果断干脆？"],
        "common_mistakes": ["点苔散乱无节奏", "苔点过多过密", "位置不在结构转折处"],
    },
    {
        "title": "染色/调整",
        "instruction": "如果是水墨山水则跳过染色，直接调整整体黑白灰和疏密关系。设色山水用羊毫淡染赭石（山体阳面）和花青（山体阴面）。色不碍墨，墨不碍色。最后整体调整：少加多减，宁简勿繁。",
        "materials": [MATERIALS["landscape_brush_sheep"], MATERIALS["paper_shengxuan"], MATERIALS["color_xieyi"]],
        "checklist": ["水墨山水是否跳过染色？", "设色是否淡而透？", "色是否压了墨？", "整体黑白疏密是否和谐？"],
        "common_mistakes": ["染色过浓压墨", "水墨山水强行染色", "越改越乱"],
    },
]

# ============ 皴法难点提示 ============

CUNFA_TIPS = [
    "笔中水分要少：蘸墨后在废纸上吸去多余水分，笔尖微微发涩才是正确状态",
    "中锋行笔：笔杆垂直纸面，笔尖始终在线条中央",
    "行笔肯定但不宜太快：以均匀速度行笔，让线条有节奏感",
    "自然出现的飞白即正确皴法：笔中水分少、行笔有速度，飞白自然呈现",
    "不要刻意回填空白：飞白是皴法的「呼吸」，填平了就失去了层次感",
]


def get_course_steps(method: str, genre: str) -> List[Dict[str, Any]]:
    """根据画法和画种返回完整步骤模板"""
    if method == "gongbi" and genre == "flower_bird":
        return STEPS_GONGBI_FLOWER_BIRD
    elif method == "gongbi" and genre == "landscape":
        # 工笔山水与花鸟五步结构相同
        return STEPS_GONGBI_FLOWER_BIRD
    elif method == "xieyi" and genre == "flower_bird":
        return STEPS_XIEYI_FLOWER_BIRD
    elif method == "xieyi" and genre == "landscape":
        return STEPS_XIEYI_LANDSCAPE
    return STEPS_GONGBI_FLOWER_BIRD  # fallback


def get_method_material_brief(method: str, genre: str) -> Dict[str, List[MaterialItem]]:
    """按画种+画法返回画材推荐"""
    result = {"笔": [], "纸": [], "墨": [], "色": []}
    steps = get_course_steps(method, genre)
    seen = set()
    for step in steps:
        for m in step.get("materials", []):
            key = f"{m.category}:{m.name}"
            if key not in seen:
                seen.add(key)
                cat_map = {"brush": "笔", "paper": "纸", "ink": "墨", "color": "色"}
                cat = cat_map.get(m.category, m.category)
                result[cat].append(m)
    return result


def get_cunfa_tips() -> List[str]:
    """皴法五大要点"""
    return CUNFA_TIPS
