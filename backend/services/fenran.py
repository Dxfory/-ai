"""独立分染示意图生成服务。

分染模块只读取原画和上一阶段白描稿，不修改、不覆盖白描模块输出。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat


@dataclass
class FenranStepResult:
    step_num: int
    title: str
    instruction: str
    output_path: str


@dataclass
class FenranObject:
    object_id: str
    object_type: str
    bbox: tuple[int, int, int, int]
    mask: Image.Image
    average_color: tuple[int, int, int]
    shadow_color: tuple[int, int, int]
    pigment: str
    fenran_color: tuple[int, int, int]
    confidence: float
    participates: bool = True


@dataclass
class FenranResult:
    output_dir: str
    preview_path: str
    steps: list[FenranStepResult]
    metadata: dict


PIGMENTS = {
    "淡胭脂": (196, 82, 99),
    "曙红": (207, 72, 86),
    "朱磦": (205, 93, 62),
    "藤黄": (218, 176, 58),
    "花青": (55, 105, 128),
    "汁绿": (88, 137, 74),
    "草绿": (95, 151, 83),
    "赭石": (155, 103, 69),
    "淡赭石": (176, 130, 91),
    "淡墨": (92, 88, 78),
    "赭墨": (104, 72, 51),
}

TYPE_COLORS = {
    "leaf": (70, 150, 75),
    "leaf_back": (176, 130, 91),
    "bud": (176, 130, 91),
    "red_flower": (210, 75, 95),
    "white_flower": (190, 145, 95),
    "fruit": (220, 172, 50),
    "branch": (130, 85, 55),
    "bird": (90, 115, 120),
    "insect": (120, 120, 95),
    "background": (185, 185, 185),
}

FENRAN_RULES = [
    "先从原画做像素级色彩分离，再由白描线约束对象边界。",
    "背景区默认排除，不参与分染。",
    "绿色叶用绿色系，红粉花用红色系，白花用淡赭或淡墨暗部分染，果、枝、鸟、虫分开处理。",
    "每个对象内部单独寻找暗部、根部、遮挡处，并由深向浅退晕。",
]


def generate_fenran_steps(
    reference_path: str,
    line_draft_path: str,
    output_dir: str,
    task_id: str,
    subject_hint: str = "",
    palette_hint: list[str] | None = None,
    step_count: int = 5,
) -> FenranResult:
    """生成从原画分离出的分染步骤图。"""
    del palette_hint, subject_hint
    task_dir = Path(output_dir) / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    line = Image.open(line_draft_path).convert("RGB")
    line = _resize_for_fenran_work(line)
    reference = _fit_reference(reference_path, line.size)
    line_mask = _line_layer(line)
    segmentation = _segment_source_colors(reference, line_mask)
    line_candidates = _line_shape_candidates(line_mask, reference)
    objects = _build_objects(reference, segmentation, line_candidates=line_candidates)

    steps: list[FenranStepResult] = []
    base_path = task_dir / "step_01_base_line.png"
    line.save(base_path)
    steps.append(FenranStepResult(
        1,
        "白描骨架",
        "读取上一阶段白描结果作为只读骨架。",
        str(base_path),
    ))

    color_debug_path = task_dir / "step_02_color_segmentation.png"
    _render_color_segmentation(segmentation, color_debug_path)
    steps.append(FenranStepResult(
        2,
        "原画色彩分割",
        "先把原画分成绿叶、红粉花、白花、黄果、枝干和排除背景。",
        str(color_debug_path),
    ))

    object_debug_path = task_dir / "step_03_object_masks.png"
    _render_object_masks(line, objects, object_debug_path, line_candidates=line_candidates)
    steps.append(FenranStepResult(
        3,
        "对象区域约束",
        "将色彩区域拆成对象 mask，颜色只允许落在对象内部。",
        str(object_debug_path),
    ))

    quality = _evaluate_segmentation(segmentation, objects, reference.size)
    if not quality["passed"]:
        return FenranResult(
            output_dir=str(task_dir),
            preview_path=str(object_debug_path),
            steps=steps,
            metadata={
                "status": "segmentation_failed",
                "reason": quality["reason"],
                "quality": quality,
                "rules": FENRAN_RULES,
                "line_draft_read_only": True,
                "background_colored": False,
                "should_render_fenran": False,
                "objects": [_object_to_metadata(obj) for obj in objects],
                "regions": [_object_to_metadata(obj) for obj in objects],
                "line_candidates": line_candidates,
            },
        )

    accumulated = Image.new("RGBA", line.size, (255, 255, 255, 0))
    render_specs = [
        ("第一遍分染", "按对象原画色彩转译颜料，只在暗部和根部薄染第一遍。", 0.26, 0.50),
        ("局部加深", "继续加深遮挡、转折、叶脉两侧、花瓣根部和枝节处。", 0.32, 0.32),
        ("分染预览", "多遍薄染叠合，白描线压在最上方，背景不默认上色。", 0.18, 0.62),
    ]
    max_steps = max(4, min(6, step_count + 1))
    for index, (title, instruction, alpha, dark_fraction) in enumerate(render_specs[: max_steps - 3], start=4):
        wash = _render_wash_layer(reference, objects, alpha, dark_fraction)
        accumulated = Image.alpha_composite(accumulated, wash)
        composed = _compose_with_lines(line, accumulated, line_mask)
        step_path = task_dir / f"step_{index:02d}_fenran.png"
        composed.save(step_path)
        steps.append(FenranStepResult(index, title, instruction, str(step_path)))

    return FenranResult(
        output_dir=str(task_dir),
        preview_path=steps[-1].output_path,
        steps=steps,
        metadata={
            "status": "ready",
            "reason": "",
            "quality": quality,
            "should_render_fenran": True,
            "rules": FENRAN_RULES,
            "line_draft_read_only": True,
            "background_colored": False,
            "objects": [_object_to_metadata(obj) for obj in objects],
            "regions": [_object_to_metadata(obj) for obj in objects],
            "line_candidates": line_candidates,
        },
    )


def _fit_reference(reference_path: str, size: tuple[int, int]) -> Image.Image:
    reference = Image.open(reference_path).convert("RGB")
    reference = ImageOps.contain(reference, size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (255, 255, 255))
    canvas.paste(reference, ((size[0] - reference.width) // 2, (size[1] - reference.height) // 2))
    return canvas


def _resize_for_fenran_work(image: Image.Image, max_side: int = 1600) -> Image.Image:
    """Keep manual high-resolution uploads responsive for browser preview generation."""
    if max(image.size) <= max_side:
        return image
    scale = max_side / max(image.size)
    size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _segment_source_colors(reference: Image.Image, line_mask: Image.Image) -> dict[str, Image.Image]:
    size = reference.size
    hsv = reference.convert("HSV")
    h, s, v = hsv.split()
    paper_rgb = _estimate_paper_color(reference)

    background = _background_mask(reference, line_mask)
    non_bg = ImageOps.invert(background)
    chroma_delta = _chroma_delta_mask(reference, paper_rgb)
    texture = _texture_mask(reference)
    sat_subject = s.point(lambda p: 255 if p > 34 else 0)
    line_subject = line_mask.filter(ImageFilter.MaxFilter(21)).filter(ImageFilter.GaussianBlur(3))
    subject = ImageChops.multiply(
        non_bg,
        ImageChops.lighter(ImageChops.multiply(ImageChops.lighter(sat_subject, texture), chroma_delta), line_subject),
    )

    leaf_seed = ImageChops.multiply(
        ImageChops.lighter(_hsv_mask(h, s, v, [(50, 178)], sat_min=18, val_min=28), _green_leaf_mask(reference)),
        chroma_delta,
    )
    leaf_seed = ImageChops.multiply(leaf_seed, non_bg)
    subject_roi = _expanded_bbox_mask(_clean_mask(leaf_seed, min_area=max(60, (size[0] * size[1]) // 14000)), size, 0.22)
    leaf_near = _expand_mask(_clean_mask(leaf_seed, min_area=max(60, (size[0] * size[1]) // 14000)), 65)
    subject_near = ImageChops.multiply(
        non_bg,
        ImageChops.multiply(subject_roi, leaf_near),
    )

    masks = {
        "leaf": leaf_seed,
        "red_flower": ImageChops.multiply(_hsv_mask(h, s, v, [(0, 18), (236, 255)], sat_min=42, val_min=45), chroma_delta),
        "fruit": ImageChops.multiply(_hsv_mask(h, s, v, [(25, 48)], sat_min=46, val_min=65), chroma_delta),
        "branch": ImageChops.multiply(_relative_branch_mask(reference, paper_rgb), ImageChops.multiply(subject_near, line_subject)),
        "bird": ImageChops.multiply(_bird_mask(reference, paper_rgb), subject_near),
        "insect": Image.new("L", size, 0),
    }
    paper_like = _paper_like_mask(h, s, v)
    masks["white_flower"] = ImageChops.multiply(
        _white_flower_mask(reference),
        ImageChops.multiply(subject_near, ImageOps.invert(_expand_mask(masks["branch"], 5))),
    )

    bud_seed = ImageChops.multiply(_bud_mask(reference), subject_near)
    leaf_front, leaf_back = _split_leaf_faces(reference, ImageChops.multiply(leaf_seed, ImageOps.invert(_expand_mask(bud_seed, 3))))

    cleaned: dict[str, Image.Image] = {"background": background}
    used = Image.new("L", size, 0)
    masks["leaf"] = leaf_front
    masks["leaf_back"] = leaf_back
    masks["bud"] = bud_seed
    for key in ["bud", "leaf_back", "leaf", "red_flower", "fruit", "bird", "branch", "insect", "white_flower"]:
        mask = ImageChops.multiply(masks[key], non_bg)
        if key != "white_flower":
            mask = ImageChops.multiply(mask, subject)
        if key in {"bud", "leaf_back", "red_flower", "fruit", "branch", "bird", "insect", "white_flower"}:
            mask = ImageChops.multiply(mask, subject_near)
        mask = ImageChops.multiply(mask, ImageOps.invert(used))
        mask = _clean_mask(mask, min_area=max(60, (size[0] * size[1]) // 9000))
        cleaned[key] = mask
        used = ImageChops.lighter(used, _expand_mask(mask, 3))
    return cleaned


def _split_leaf_faces(reference: Image.Image, leaf_mask: Image.Image) -> tuple[Image.Image, Image.Image]:
    values = []
    gray = ImageOps.grayscale(reference)
    small_size = _analysis_size(reference.size)
    small_gray = gray.resize(small_size, Image.Resampling.LANCZOS)
    small_leaf = leaf_mask.resize(small_size, Image.Resampling.NEAREST)
    gp, mp = small_gray.load(), small_leaf.load()
    for y in range(small_size[1]):
        for x in range(small_size[0]):
            if mp[x, y] > 128:
                values.append(gp[x, y])
    if not values:
        return leaf_mask, Image.new("L", leaf_mask.size, 0)
    values.sort()
    threshold = values[min(len(values) - 1, int(len(values) * 0.62))]
    front = ImageChops.multiply(leaf_mask, gray.point(lambda p: 255 if p <= threshold else 0))
    back = ImageChops.multiply(leaf_mask, gray.point(lambda p: 255 if p > threshold else 0))
    return front, back


def _bud_mask(reference: Image.Image) -> Image.Image:
    pix = reference.load()
    mask = Image.new("L", reference.size, 0)
    mp = mask.load()
    for y in range(reference.height):
        for x in range(reference.width):
            r, g, b = pix[x, y]
            luma = (r + g + b) / 3
            chroma = max(r, g, b) - min(r, g, b)
            pale_gray_green = 112 <= luma <= 184 and chroma < 45 and g >= r - 8 and g >= b - 2
            if pale_gray_green:
                mp[x, y] = 255
    raw = mask.filter(ImageFilter.MedianFilter(3))
    result = Image.new("L", reference.size, 0)
    max_area = reference.width * reference.height * 0.018
    min_area = max(120, reference.width * reference.height // 24000)
    for component in _connected_components(raw, min_area=min_area, limit=24):
        bbox = component.getbbox()
        if not bbox:
            continue
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        area = _mask_area(component)
        aspect = max(width, height) / max(1, min(width, height))
        if area <= max_area and 1.0 <= aspect <= 3.2:
            result = ImageChops.lighter(result, component)
    return result


def _expanded_bbox_mask(mask: Image.Image, size: tuple[int, int], padding_ratio: float) -> Image.Image:
    bbox = mask.getbbox()
    result = Image.new("L", size, 0)
    if not bbox:
        return result
    x0, y0, x1, y1 = bbox
    pad_x = int((x1 - x0) * padding_ratio)
    pad_y = int((y1 - y0) * padding_ratio)
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(size[0], x1 + pad_x)
    y1 = min(size[1], y1 + pad_y)
    ImageDraw.Draw(result).rectangle((x0, y0, x1, y1), fill=255)
    return result


def _green_leaf_mask(reference: Image.Image) -> Image.Image:
    pix = reference.load()
    mask = Image.new("L", reference.size, 0)
    mp = mask.load()
    for y in range(reference.height):
        for x in range(reference.width):
            r, g, b = pix[x, y]
            luma = (r + g + b) / 3
            greenish = g >= r - 18 and g >= b + 4 and b >= r - 45
            muted_olive = g > 62 and 42 < luma < 185 and (g - b) > 4 and (g - r) > -22
            if greenish and muted_olive:
                mp[x, y] = 255
    return mask


def _white_flower_mask(reference: Image.Image) -> Image.Image:
    pix = reference.load()
    mask = Image.new("L", reference.size, 0)
    mp = mask.load()
    for y in range(reference.height):
        for x in range(reference.width):
            r, g, b = pix[x, y]
            luma = (r + g + b) / 3
            chroma = max(r, g, b) - min(r, g, b)
            if luma > 152 and chroma < 38 and r > 135 and g > 132 and b > 124:
                mp[x, y] = 255
    return mask


def _texture_mask(reference: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(reference)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    return edges.point(lambda p: 255 if p > 18 else 0).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(2))


def _estimate_paper_color(reference: Image.Image) -> tuple[int, int, int]:
    small = reference.resize((80, 80), Image.Resampling.LANCZOS)
    samples = []
    pix = small.load()
    for y in range(80):
        for x in range(80):
            if x < 8 or y < 8 or x >= 72 or y >= 72:
                samples.append(pix[x, y])
    if not samples:
        return (235, 230, 215)
    return tuple(sorted(channel)[len(channel) // 2] for channel in zip(*samples))


def _chroma_delta_mask(reference: Image.Image, paper_rgb: tuple[int, int, int]) -> Image.Image:
    pix = reference.load()
    mask = Image.new("L", reference.size, 0)
    mp = mask.load()
    pr, pg, pb = paper_rgb
    for y in range(reference.height):
        for x in range(reference.width):
            r, g, b = pix[x, y]
            # Compare against paper after removing shared brightness shift.
            delta = max(abs((r - g) - (pr - pg)), abs((g - b) - (pg - pb)), abs((r - b) - (pr - pb)))
            luminance_delta = abs((r + g + b) // 3 - (pr + pg + pb) // 3)
            if delta > 18 or luminance_delta > 42:
                mp[x, y] = 255
    return mask


def _relative_branch_mask(reference: Image.Image, paper_rgb: tuple[int, int, int]) -> Image.Image:
    pix = reference.load()
    mask = Image.new("L", reference.size, 0)
    mp = mask.load()
    paper_luma = sum(paper_rgb) / 3
    for y in range(reference.height):
        for x in range(reference.width):
            r, g, b = pix[x, y]
            luma = (r + g + b) / 3
            warm = r >= g >= b or r >= b >= g
            if warm and luma < paper_luma - 44 and r - b > 12:
                mp[x, y] = 255
    return mask


def _bird_mask(reference: Image.Image, paper_rgb: tuple[int, int, int]) -> Image.Image:
    pix = reference.load()
    mask = Image.new("L", reference.size, 0)
    mp = mask.load()
    paper_luma = sum(paper_rgb) / 3
    for y in range(reference.height):
        for x in range(reference.width):
            r, g, b = pix[x, y]
            luma = (r + g + b) / 3
            cool_or_dark = b >= r - 8 or g >= r - 8
            if cool_or_dark and luma < paper_luma - 34:
                mp[x, y] = 255
    return mask


def _background_mask(reference: Image.Image, line_mask: Image.Image) -> Image.Image:
    small_size = _analysis_size(reference.size)
    small_ref = reference.resize(small_size, Image.Resampling.LANCZOS)
    small_line = line_mask.resize(small_size, Image.Resampling.NEAREST)
    hsv = small_ref.convert("HSV")
    _, s, v = hsv.split()
    paper = ImageChops.lighter(
        s.point(lambda p: 255 if p < 44 else 0),
        v.point(lambda p: 255 if p > 214 else 0),
    )
    paper = ImageChops.multiply(paper, ImageOps.invert(small_line.filter(ImageFilter.MaxFilter(5))))
    bg_small = _flood_from_edges(paper)
    return bg_small.resize(reference.size, Image.Resampling.NEAREST).filter(ImageFilter.MaxFilter(5))


def _flood_from_edges(passable: Image.Image) -> Image.Image:
    width, height = passable.size
    pix = passable.load()
    out = Image.new("L", passable.size, 0)
    out_pix = out.load()
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))
    while queue:
        x, y = queue.popleft()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        if out_pix[x, y] or pix[x, y] < 128:
            continue
        out_pix[x, y] = 255
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return out


def _hsv_mask(
    h: Image.Image,
    s: Image.Image,
    v: Image.Image,
    ranges: list[tuple[int, int]],
    sat_min: int,
    val_min: int,
    val_max: int = 255,
) -> Image.Image:
    hp, sp, vp = h.load(), s.load(), v.load()
    mask = Image.new("L", h.size, 0)
    mp = mask.load()
    for y in range(h.height):
        for x in range(h.width):
            hue = hp[x, y]
            if sp[x, y] >= sat_min and val_min <= vp[x, y] <= val_max and any(a <= hue <= b for a, b in ranges):
                mp[x, y] = 255
    return mask


def _paper_like_mask(h: Image.Image, s: Image.Image, v: Image.Image) -> Image.Image:
    del h
    sp, vp = s.load(), v.load()
    mask = Image.new("L", s.size, 0)
    mp = mask.load()
    for y in range(s.height):
        for x in range(s.width):
            if sp[x, y] < 34 and vp[x, y] > 168:
                mp[x, y] = 255
    return mask


def _line_shape_candidates(line_mask: Image.Image, reference: Image.Image) -> list[dict]:
    expanded = line_mask.filter(ImageFilter.MaxFilter(9))
    components = _connected_components(expanded, min_area=max(140, line_mask.width * line_mask.height // 16000), limit=48)
    candidates: list[dict] = []
    for idx, component in enumerate(components, start=1):
        bbox = component.getbbox()
        if not bbox:
            continue
        x0, y0, x1, y1 = bbox
        width = max(1, x1 - x0)
        height = max(1, y1 - y0)
        area = _mask_area(component)
        box_area = width * height
        fill = area / max(1, box_area)
        aspect = max(width, height) / max(1, min(width, height))
        avg = _average_color(reference, component)
        color_type = _color_type(avg)
        scores = {
            "branch": 0.0,
            "leaf": 0.0,
            "fruit": 0.0,
            "flower": 0.0,
            "bird": 0.0,
            "insect": 0.0,
        }
        if aspect > 4.0 and fill < 0.42:
            scores["branch"] += 0.65
        if 1.7 <= aspect <= 4.8 and fill >= 0.12:
            scores["leaf"] += 0.48
        if aspect < 1.55 and 0.10 <= fill <= 0.55:
            scores["fruit"] += 0.45
            scores["flower"] += 0.28
        if box_area > line_mask.width * line_mask.height * 0.025 and aspect < 3.0:
            scores["flower"] += 0.35
            scores["bird"] += 0.20
        if color_type == "green":
            scores["leaf"] += 0.35
        elif color_type == "yellow":
            scores["fruit"] += 0.30
        elif color_type == "red":
            scores["flower"] += 0.35
        elif color_type == "brown":
            scores["branch"] += 0.25
        elif color_type == "dark":
            scores["bird"] += 0.25
            scores["branch"] += 0.12
        best_type = max(scores, key=scores.get)
        candidates.append({
            "candidate_id": f"line_{idx:02d}",
            "bbox": list(bbox),
            "shape_type": best_type,
            "shape_scores": {key: round(value, 2) for key, value in scores.items()},
            "aspect": round(aspect, 2),
            "fill": round(fill, 3),
            "average_color": _hex(avg),
            "color_type": color_type,
        })
    return candidates


def _build_objects(
    reference: Image.Image,
    segmentation: dict[str, Image.Image],
    line_candidates: list[dict] | None = None,
) -> list[FenranObject]:
    objects: list[FenranObject] = []
    counters: dict[str, int] = {}
    order = ["bud", "leaf_back", "leaf", "red_flower", "white_flower", "fruit", "branch", "bird", "insect"]
    min_area = max(160, (reference.width * reference.height) // 14000)
    candidate_masks = _candidate_masks(reference.size, line_candidates or [])
    for object_type in order:
        for component in _connected_components(segmentation[object_type], min_area=min_area, limit=30):
            object_type = _cross_check_type(object_type, component, reference, line_candidates or [])
            counters[object_type] = counters.get(object_type, 0) + 1
            object_id = f"{object_type}_{counters[object_type]:02d}"
            avg = _average_color(reference, component)
            shadow = _shadow_color(reference, component)
            pigment, color, confidence = _pigment_for_object(object_type, avg, shadow)
            bbox = component.getbbox() or (0, 0, reference.width, reference.height)
            objects.append(FenranObject(object_id, object_type, bbox, component, avg, shadow, pigment, color, confidence))
    # Line-derived candidates are diagnostic only for now. They are too coarse for fenran fills
    # because rectangular boxes can include the fan background.
    for candidate, candidate_mask in []:
        shape_type = candidate["shape_type"]
        if shape_type not in {"leaf", "fruit", "branch", "flower", "bird", "insect"}:
            continue
        bbox = candidate["bbox"]
        box_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        if box_area > reference.width * reference.height * 0.08:
            continue
        if bbox[0] <= 2 or bbox[1] <= 2 or bbox[2] >= reference.width - 2 or bbox[3] >= reference.height - 2:
            continue
        mapped_type = "white_flower" if shape_type == "flower" else shape_type
        if _overlaps_existing(candidate_mask, objects):
            continue
        if _mask_area(candidate_mask) < min_area:
            continue
        counters[mapped_type] = counters.get(mapped_type, 0) + 1
        object_id = f"{mapped_type}_{counters[mapped_type]:02d}"
        avg = _average_color(reference, candidate_mask)
        shadow = _shadow_color(reference, candidate_mask)
        pigment, color, confidence = _pigment_for_object(mapped_type, avg, shadow)
        bbox = candidate_mask.getbbox() or (0, 0, reference.width, reference.height)
        objects.append(FenranObject(object_id, mapped_type, bbox, candidate_mask, avg, shadow, pigment, color, confidence * 0.75))
    objects.sort(key=lambda obj: _mask_area(obj.mask), reverse=True)
    return objects[:36]


def _candidate_masks(size: tuple[int, int], candidates: list[dict]) -> list[tuple[dict, Image.Image]]:
    result = []
    for candidate in candidates:
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle(tuple(candidate["bbox"]), fill=255)
        result.append((candidate, mask))
    return result


def _overlaps_existing(mask: Image.Image, objects: list[FenranObject]) -> bool:
    area = _mask_area(mask)
    if area == 0:
        return True
    for obj in objects:
        overlap = _mask_area(ImageChops.multiply(mask, obj.mask))
        if overlap / area > 0.35:
            return True
    return False


def _cross_check_type(
    color_type: str,
    mask: Image.Image,
    reference: Image.Image,
    candidates: list[dict],
) -> str:
    bbox = mask.getbbox()
    if not bbox:
        return color_type
    avg = _average_color(reference, mask)
    evidence_color = _color_type(avg)
    best_shape = _best_overlapping_shape(bbox, candidates)
    if not best_shape:
        return color_type
    shape_type = best_shape["shape_type"]
    if color_type == "leaf":
        return "leaf"
    if shape_type == "leaf" and color_type in {"fruit", "red_flower", "white_flower"} and evidence_color in {"green", "neutral"}:
        return "leaf"
    if shape_type == "fruit" and color_type in {"branch", "red_flower"} and evidence_color in {"yellow", "brown", "neutral"}:
        return "fruit"
    if shape_type == "branch" and color_type in {"fruit", "red_flower", "white_flower"}:
        return "branch"
    if shape_type == "bird" and color_type in {"branch", "fruit"} and evidence_color in {"dark", "neutral", "brown"}:
        return "bird"
    return color_type


def _best_overlapping_shape(bbox: tuple[int, int, int, int], candidates: list[dict]) -> dict | None:
    best = None
    best_overlap = 0
    for candidate in candidates:
        cb = candidate["bbox"]
        x0 = max(bbox[0], cb[0])
        y0 = max(bbox[1], cb[1])
        x1 = min(bbox[2], cb[2])
        y1 = min(bbox[3], cb[3])
        overlap = max(0, x1 - x0) * max(0, y1 - y0)
        if overlap > best_overlap:
            best = candidate
            best_overlap = overlap
    if not best or best_overlap < 64:
        return None
    return best


def _connected_components(mask: Image.Image, min_area: int, limit: int) -> list[Image.Image]:
    small_size = _analysis_size(mask.size)
    small = mask.resize(small_size, Image.Resampling.NEAREST).point(lambda p: 255 if p > 128 else 0)
    width, height = small.size
    pix = small.load()
    seen = bytearray(width * height)
    comps: list[tuple[int, tuple[int, int, int, int], list[tuple[int, int]]]] = []
    for y in range(height):
        for x in range(width):
            idx = y * width + x
            if seen[idx] or pix[x, y] < 128:
                continue
            queue = deque([(x, y)])
            seen[idx] = 1
            points: list[tuple[int, int]] = []
            x0 = x1 = x
            y0 = y1 = y
            while queue:
                cx, cy = queue.popleft()
                points.append((cx, cy))
                x0, x1 = min(x0, cx), max(x1, cx)
                y0, y1 = min(y0, cy), max(y1, cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    nidx = ny * width + nx
                    if seen[nidx] or pix[nx, ny] < 128:
                        continue
                    seen[nidx] = 1
                    queue.append((nx, ny))
            if len(points) >= max(8, int(min_area * (small_size[0] * small_size[1]) / (mask.width * mask.height))):
                comps.append((len(points), (x0, y0, x1 + 1, y1 + 1), points))
    comps.sort(key=lambda item: item[0], reverse=True)
    result: list[Image.Image] = []
    for _, _, points in comps[:limit]:
        comp = Image.new("L", small_size, 0)
        cp = comp.load()
        for px, py in points:
            cp[px, py] = 255
        full = comp.resize(mask.size, Image.Resampling.NEAREST)
        full = _clean_mask(full, min_area=min_area)
        if _mask_area(full) >= min_area:
            result.append(full)
    return result


def _render_wash_layer(reference: Image.Image, objects: list[FenranObject], alpha: float, dark_fraction: float) -> Image.Image:
    layer = Image.new("RGBA", reference.size, (255, 255, 255, 0))
    for obj in objects:
        if not obj.participates:
            continue
        local_dark_fraction = dark_fraction
        if obj.object_type in {"leaf", "leaf_back", "bud"}:
            local_dark_fraction = min(dark_fraction, 0.12 if obj.object_type == "leaf" else 0.16)
        dark = _dark_area_mask(reference, obj.mask, local_dark_fraction)
        if obj.object_type == "white_flower":
            object_alpha = alpha * 0.42
        elif obj.object_type in {"leaf", "leaf_back", "bud"}:
            object_alpha = alpha * (0.70 if obj.object_type == "leaf" else 0.58)
            dark = _shrink_soft_mask(dark, 11 if obj.object_type == "leaf" else 7)
        elif obj.object_type == "branch":
            object_alpha = alpha * 0.72
        else:
            object_alpha = alpha
        wash = Image.new("RGBA", reference.size, obj.fenran_color + (0,))
        blur = max(3, min(reference.size) // (260 if obj.object_type in {"leaf", "leaf_back", "bud"} else 130))
        soft = dark.filter(ImageFilter.GaussianBlur(blur))
        wash.putalpha(soft.point(lambda p: int(p * object_alpha)))
        layer = Image.alpha_composite(layer, wash)
    return layer


def _shrink_soft_mask(mask: Image.Image, size: int) -> Image.Image:
    result = mask.point(lambda p: 255 if p > 96 else 0)
    for _ in range(max(1, size // 2)):
        result = result.filter(ImageFilter.MinFilter(3))
    return result.filter(ImageFilter.MaxFilter(3))


def _evaluate_segmentation(
    segmentation: dict[str, Image.Image],
    objects: list[FenranObject],
    size: tuple[int, int],
) -> dict:
    total_area = size[0] * size[1]
    background_area = _mask_area(segmentation["background"])
    object_areas = {
        key: _mask_area(segmentation[key])
        for key in ["bud", "leaf_back", "leaf", "red_flower", "white_flower", "fruit", "branch", "bird", "insect"]
        if key in segmentation
    }
    object_counts: dict[str, int] = {}
    object_area_total = 0
    for obj in objects:
        area = _mask_area(obj.mask)
        object_area_total += area
        object_counts[obj.object_type] = object_counts.get(obj.object_type, 0) + 1

    present_types = [key for key, area in object_areas.items() if area / max(1, total_area) >= 0.003]
    reasons = []
    if len(present_types) < 2:
        reasons.append("色彩分割未识别出至少两类可分染对象")
    object_area_ratio = object_area_total / max(1, total_area)
    if object_area_ratio < 0.018:
        reasons.append("可参与分染的对象面积过小")
    if background_area / max(1, total_area) > 0.90:
        reasons.append("背景或纸色占比过高，原画色彩信息不足或白描与原画不对齐")
    if not objects:
        reasons.append("没有生成有效对象 mask")
    dominant_non_leaf = (object_areas.get("red_flower", 0) + object_areas.get("fruit", 0)) / max(1, total_area)
    dominant_warm_structures = (
        object_areas.get("fruit", 0) + object_areas.get("branch", 0)
    ) / max(1, total_area)
    if object_areas.get("leaf", 0) == 0 and dominant_non_leaf > 0.35:
        reasons.append("色彩阈值可能把纸色或主体灰褐误判为花/果，未可靠识别叶片")
    if object_areas.get("leaf", 0) == 0 and dominant_warm_structures > 0.22:
        reasons.append("未识别到叶片，却出现大面积黄/褐对象，疑似把线稿暗部或纸色当成可分染对象")
    if object_area_ratio > 0.45:
        reasons.append("对象 mask 覆盖过大，疑似把背景或整图色调当成可分染对象")

    return {
        "passed": not reasons,
        "reason": "；".join(reasons),
        "present_types": present_types,
        "object_counts": object_counts,
        "object_areas": object_areas,
        "object_area_ratio": round(object_area_ratio, 4),
        "background_ratio": round(background_area / max(1, total_area), 4),
    }


def _dark_area_mask(reference: Image.Image, object_mask: Image.Image, dark_fraction: float) -> Image.Image:
    gray = ImageOps.grayscale(reference)
    values = []
    small_size = _analysis_size(reference.size)
    small_gray = gray.resize(small_size, Image.Resampling.LANCZOS)
    small_mask = object_mask.resize(small_size, Image.Resampling.NEAREST)
    gp, mp = small_gray.load(), small_mask.load()
    for y in range(small_size[1]):
        for x in range(small_size[0]):
            if mp[x, y] > 128:
                values.append(gp[x, y])
    if not values:
        return object_mask
    values.sort()
    threshold = values[min(len(values) - 1, int(len(values) * dark_fraction))]
    dark = gray.point(lambda p: 255 if p <= threshold + 12 else max(0, 255 - (p - threshold - 12) * 5))
    dark = ImageChops.multiply(object_mask, dark)
    if ImageStat.Stat(dark).sum[0] < 255:
        return object_mask.point(lambda p: int(p * 0.5))
    return dark


def _render_color_segmentation(segmentation: dict[str, Image.Image], output_path: Path) -> None:
    size = next(iter(segmentation.values())).size
    canvas = Image.new("RGBA", size, (255, 255, 252, 255))
    for key in ["background", "bud", "leaf_back", "leaf", "red_flower", "white_flower", "fruit", "branch", "bird", "insect"]:
        if key not in segmentation:
            continue
        color = TYPE_COLORS[key]
        overlay = Image.new("RGBA", size, color + (0,))
        alpha = 90 if key == "background" else 150
        overlay.putalpha(segmentation[key].point(lambda p: alpha if p > 0 else 0))
        canvas = Image.alpha_composite(canvas, overlay)
    canvas.convert("RGB").save(output_path)


def _render_object_masks(
    line: Image.Image,
    objects: list[FenranObject],
    output_path: Path,
    line_candidates: list[dict] | None = None,
) -> None:
    canvas = Image.new("RGBA", line.size, (255, 255, 252, 255))
    for obj in objects:
        color = TYPE_COLORS.get(obj.object_type, (120, 120, 120))
        overlay = Image.new("RGBA", line.size, color + (0,))
        overlay.putalpha(obj.mask.point(lambda p: 105 if p > 0 else 0))
        canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)
    for candidate in (line_candidates or [])[:24]:
        bbox = tuple(candidate["bbox"])
        draw.rectangle(bbox, outline=(80, 80, 80, 180), width=2)
        draw.text((bbox[0] + 4, max(0, bbox[1] - 14)), candidate["shape_type"], fill=(50, 50, 50, 255))
    for obj in objects[:20]:
        draw.rectangle(obj.bbox, outline=TYPE_COLORS.get(obj.object_type, (120, 120, 120)) + (255,), width=3)
        draw.text((obj.bbox[0] + 5, obj.bbox[1] + 5), f"{obj.object_id} {obj.pigment}", fill=(20, 20, 20, 255))
    ink = Image.new("RGBA", line.size, (20, 22, 20, 0))
    ink.putalpha(_line_layer(line))
    Image.alpha_composite(canvas, ink).convert("RGB").save(output_path)


def _compose_with_lines(line: Image.Image, wash: Image.Image, line_mask: Image.Image) -> Image.Image:
    paper = Image.new("RGBA", line.size, (255, 255, 252, 255))
    paper = Image.alpha_composite(paper, wash)
    ink = Image.new("RGBA", line.size, (24, 28, 24, 0))
    ink.putalpha(line_mask)
    return Image.alpha_composite(paper, ink).convert("RGB")


def _pigment_for_object(
    object_type: str,
    avg: tuple[int, int, int],
    shadow: tuple[int, int, int],
) -> tuple[str, tuple[int, int, int], float]:
    del avg, shadow
    if object_type == "leaf":
        return "汁绿", PIGMENTS["汁绿"], 0.86
    if object_type == "leaf_back":
        return "淡赭石", PIGMENTS["淡赭石"], 0.80
    if object_type == "bud":
        return "淡赭石", PIGMENTS["淡赭石"], 0.82
    if object_type == "red_flower":
        return "淡胭脂", PIGMENTS["淡胭脂"], 0.84
    if object_type == "white_flower":
        return "淡赭石", PIGMENTS["淡赭石"], 0.82
    if object_type == "fruit":
        return "藤黄", PIGMENTS["藤黄"], 0.78
    if object_type == "branch":
        return "赭墨", PIGMENTS["赭墨"], 0.76
    if object_type == "bird":
        return "淡墨", PIGMENTS["淡墨"], 0.70
    if object_type == "insect":
        return "淡墨", PIGMENTS["淡墨"], 0.60
    return "淡墨", PIGMENTS["淡墨"], 0.45


def _color_type(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    if mx < 95:
        return "dark"
    if mx - mn < 18:
        return "neutral"
    if g > r + 8 and g > b + 6:
        return "green"
    if r > g + 14 and r > b + 14:
        return "red"
    if r >= g >= b and r - b > 18:
        if r > 145 and g > 110:
            return "yellow"
        return "brown"
    if b >= r and b >= g:
        return "dark"
    return "neutral"


def _average_color(image: Image.Image, mask: Image.Image) -> tuple[int, int, int]:
    stat = ImageStat.Stat(image, mask)
    if not stat.count[0]:
        return (245, 245, 245)
    return tuple(int(v) for v in stat.mean[:3])


def _shadow_color(image: Image.Image, mask: Image.Image) -> tuple[int, int, int]:
    gray = ImageOps.grayscale(image)
    dark = ImageChops.multiply(mask, gray.point(lambda p: 255 if p < 178 else max(0, 255 - (p - 178) * 4)))
    if ImageStat.Stat(dark).sum[0] < 255:
        return _average_color(image, mask)
    return _average_color(image, dark)


def _line_layer(line: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(line)
    ink = ImageOps.invert(gray).point(lambda p: 255 if p > 35 else 0)
    return ink.filter(ImageFilter.MaxFilter(3))


def _clean_mask(mask: Image.Image, min_area: int) -> Image.Image:
    cleaned = mask.point(lambda p: 255 if p > 128 else 0)
    cleaned = cleaned.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    if _mask_area(cleaned) < min_area:
        return Image.new("L", mask.size, 0)
    return cleaned


def _expand_mask(mask: Image.Image, size: int) -> Image.Image:
    result = mask
    for _ in range(max(1, size // 2)):
        result = result.filter(ImageFilter.MaxFilter(3))
    return result


def _mask_area(mask: Image.Image) -> int:
    return int(ImageStat.Stat(mask).sum[0] / 255)


def _analysis_size(size: tuple[int, int]) -> tuple[int, int]:
    scale = min(1.0, 760 / max(size))
    return max(1, int(size[0] * scale)), max(1, int(size[1] * scale))


def _object_to_metadata(obj: FenranObject) -> dict:
    return {
        "region_id": obj.object_id,
        "object_id": obj.object_id,
        "bbox": list(obj.bbox),
        "object_type": obj.object_type,
        "average_color": _hex(obj.average_color),
        "shadow_color": _hex(obj.shadow_color),
        "fenran_color": _hex(obj.fenran_color),
        "pigment": obj.pigment,
        "confidence": obj.confidence,
        "participates": obj.participates,
        "start_area": "对象内部暗部、根部、遮挡处或转折处",
        "fade_direction": "从暗部向对象内部亮部退晕",
    }


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)
