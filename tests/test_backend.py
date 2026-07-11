"""backend API 测试 (使用 TestClient)"""

import io
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from backend.app import app
from backend.database import init_db
from backend.services.baimiao_knowledge import BOOK_001_LINE_LOGIC, PAIR_REFERENCE_LINE_LOGIC
from backend.services.line_draft import (
    BAIMIAO_PROMPT,
    _bbox_stats_to_dict,
    _composition_delta,
    _composition_warning,
    _detect_artwork_region_mask,
    _image_bbox_stats,
    _post_baimiao_edit_without_status_check,
    _prepare_api_image,
    _repair_short_line_gaps,
    _resolve_generation_canvas,
    _resolve_image_size,
    _smooth_junction_blobs,
    _restore_source_aspect,
    _restore_round_border_from_original,
)

init_db()
client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["server"] == "国画临摹AI教练"


def test_baimiao_prompt_forbids_hallucinated_objects():
    assert "原图没有鸟，就绝对不要画鸟" in BAIMIAO_PROMPT
    assert "任务不是创作新画" in BAIMIAO_PROMPT
    assert "输入图中没有的任何对象" in BAIMIAO_PROMPT
    assert "线稿不得越界" in BAIMIAO_PROMPT
    assert "补全必要结构线" not in BAIMIAO_PROMPT
    assert "鸟体等" not in BAIMIAO_PROMPT
    assert "严禁放大、缩小、拉伸、压扁、平移或重新排布主体" in BAIMIAO_PROMPT


def test_baimiao_prompt_includes_book_and_pair_learning_logic():
    assert "教材 33 页白描/线描共识" in BOOK_001_LINE_LOGIC
    assert "叶缘随卷曲起伏" in BOOK_001_LINE_LOGIC
    assert "原画/理想白描对照" not in BOOK_001_LINE_LOGIC
    assert "微信图片_20260710131442_2_3.jpg" in PAIR_REFERENCE_LINE_LOGIC
    assert "9cc8969d57de41ec82f2c16249d2419e.png" in PAIR_REFERENCE_LINE_LOGIC
    assert "微信图片_20260710213615_5_3.jpg" in PAIR_REFERENCE_LINE_LOGIC
    assert "4da4b5d3486243cdab1c44ea3545ff81.png" in PAIR_REFERENCE_LINE_LOGIC
    assert "73802f1c52bbc4004b852b6f8dbde788.jpg" in PAIR_REFERENCE_LINE_LOGIC
    assert "55325c3597e1db77ac80ff42525aa913.jpg" in PAIR_REFERENCE_LINE_LOGIC
    assert "白描稿必须能与原图重叠检查" in BAIMIAO_PROMPT


def test_baimiao_auto_size_resolves_to_supported_size(tmp_path, monkeypatch):
    monkeypatch.setenv("BAIMIAO_IMAGE_SIZE", "auto")
    image_path = tmp_path / "wide.png"
    Image.new("RGB", (1200, 800), "white").save(image_path)

    assert _resolve_image_size(str(image_path)) == "1536x1024"


def test_generation_canvas_contains_wide_source_without_cropping(tmp_path, monkeypatch):
    monkeypatch.setenv("BAIMIAO_IMAGE_SIZE", "auto")
    monkeypatch.setenv("BAIMIAO_PRESERVE_SOURCE_ASPECT", "true")
    image_path = tmp_path / "wide.png"
    Image.new("RGB", (1440, 1224), "white").save(image_path)

    canvas = _resolve_generation_canvas(str(image_path))

    assert canvas.request_size == "1536x1024"
    assert canvas.source_size == (1440, 1224)
    assert canvas.canvas_size == (1536, 1024)
    assert canvas.content_box[1] == 0
    assert canvas.content_box[3] == 1024
    assert canvas.content_box[2] - canvas.content_box[0] == 1205


def test_generation_canvas_contains_tall_source_without_cropping(tmp_path, monkeypatch):
    monkeypatch.setenv("BAIMIAO_IMAGE_SIZE", "auto")
    monkeypatch.setenv("BAIMIAO_PRESERVE_SOURCE_ASPECT", "true")
    image_path = tmp_path / "tall.png"
    Image.new("RGB", (800, 1400), "white").save(image_path)

    canvas = _resolve_generation_canvas(str(image_path))

    assert canvas.request_size == "1024x1536"
    assert canvas.source_size == (800, 1400)
    assert canvas.canvas_size == (1024, 1536)
    assert canvas.content_box[0] > 0
    assert canvas.content_box[1] == 0
    assert canvas.content_box[3] == 1536


def test_prepare_api_image_uses_canvas_content_box(tmp_path, monkeypatch):
    monkeypatch.setenv("BAIMIAO_IMAGE_SIZE", "1024x1024")
    monkeypatch.setenv("BAIMIAO_PRESERVE_SOURCE_ASPECT", "true")
    image_path = tmp_path / "wide.png"
    output_path = tmp_path / "api.jpg"
    source = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(source)
    draw.rectangle((0, 0, 399, 199), fill="black")
    source.save(image_path)

    canvas = _resolve_generation_canvas(str(image_path))
    _prepare_api_image(str(image_path), str(output_path), canvas=canvas)

    prepared = Image.open(output_path).convert("RGB")
    assert prepared.size == (1024, 1024)
    assert prepared.getpixel((512, 20)) == (255, 255, 255)
    assert prepared.getpixel((512, 512))[0] < 10


def test_restore_source_aspect_returns_original_size(tmp_path, monkeypatch):
    monkeypatch.setenv("BAIMIAO_IMAGE_SIZE", "1024x1024")
    monkeypatch.setenv("BAIMIAO_PRESERVE_SOURCE_ASPECT", "true")
    image_path = tmp_path / "wide.png"
    Image.new("RGB", (400, 200), "white").save(image_path)
    canvas = _resolve_generation_canvas(str(image_path))
    generated = Image.new("L", (1254, 1254), 255)
    draw = ImageDraw.Draw(generated)
    draw.rectangle((0, 313, 1253, 940), outline=0, width=3)

    restored = _restore_source_aspect(generated, canvas)

    assert restored.size == (400, 200)


def test_repair_short_line_gaps_closes_small_gap():
    img = Image.new("L", (12, 5), 255)
    draw = ImageDraw.Draw(img)
    draw.line((1, 2, 4, 2), fill=0)
    draw.line((8, 2, 10, 2), fill=0)

    repaired = _repair_short_line_gaps(img, 3)

    assert all(repaired.getpixel((x, 2)) == 0 for x in range(1, 11))


def test_repair_short_line_gaps_leaves_large_gap():
    img = Image.new("L", (14, 5), 255)
    draw = ImageDraw.Draw(img)
    draw.line((1, 2, 3, 2), fill=0)
    draw.line((9, 2, 12, 2), fill=0)

    repaired = _repair_short_line_gaps(img, 3)

    assert all(repaired.getpixel((x, 2)) == 255 for x in range(4, 9))


def test_structure_guide_is_used_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("BAIMIAO_USE_STRUCTURE_GUIDE", raising=False)
    source_path = tmp_path / "source.png"
    guide_path = tmp_path / "guide.png"
    Image.new("RGB", (20, 20), "white").save(source_path)
    Image.new("L", (20, 20), 255).save(guide_path)

    class FakeResponse:
        status_code = 200

    class FakeClient:
        def __init__(self):
            self.file_counts = []

        def post(self, url, headers, data, files):
            self.file_counts.append(len(files) if isinstance(files, list) else len(files))
            return FakeResponse()

    client = FakeClient()
    response, guide_used = _post_baimiao_edit_without_status_check(
        client=client,
        url="https://example.test/v1/images/edits",
        headers={},
        data={},
        source_path=str(source_path),
        guide_path=str(guide_path),
    )

    assert response.status_code == 200
    assert guide_used is True
    assert client.file_counts == [2]


def test_bbox_stats_and_composition_warning_detect_scale_drift():
    reference = Image.new("L", (100, 100), 255)
    ImageDraw.Draw(reference).rectangle((20, 20, 80, 80), fill=0)
    candidate = Image.new("L", (100, 100), 255)
    ImageDraw.Draw(candidate).rectangle((30, 20, 70, 80), fill=0)

    reference_stats = _image_bbox_stats(reference)
    candidate_stats = _image_bbox_stats(candidate)
    delta = _composition_delta(reference_stats, candidate_stats)

    assert _bbox_stats_to_dict(reference_stats)["bbox"] == [20, 20, 81, 81]
    assert delta["ratio_delta"] > 0.04
    assert _composition_warning(delta) is True


def test_composition_warning_allows_matching_boxes():
    reference = Image.new("L", (100, 100), 255)
    ImageDraw.Draw(reference).rectangle((20, 20, 80, 80), fill=0)
    candidate = Image.new("L", (100, 100), 255)
    ImageDraw.Draw(candidate).rectangle((21, 20, 81, 80), fill=0)

    delta = _composition_delta(_image_bbox_stats(reference), _image_bbox_stats(candidate))

    assert _composition_warning(delta) is False


def test_smooth_junction_blobs_removes_corner_bulk_without_erasing_cross():
    img = Image.new("L", (9, 9), 255)
    draw = ImageDraw.Draw(img)
    draw.line((1, 4, 7, 4), fill=0)
    draw.line((4, 1, 4, 7), fill=0)
    draw.rectangle((3, 3, 5, 5), fill=0)

    smoothed = _smooth_junction_blobs(img, 3)

    assert smoothed.getpixel((4, 4)) == 0
    assert smoothed.getpixel((1, 4)) == 0
    assert smoothed.getpixel((4, 1)) == 0
    assert smoothed.getpixel((3, 3)) == 255


def test_smooth_junction_blobs_keeps_thin_cross():
    img = Image.new("L", (9, 9), 255)
    draw = ImageDraw.Draw(img)
    draw.line((1, 4, 7, 4), fill=0)
    draw.line((4, 1, 4, 7), fill=0)

    smoothed = _smooth_junction_blobs(img, 3)

    assert all(smoothed.getpixel((x, 4)) == 0 for x in range(1, 8))
    assert all(smoothed.getpixel((4, y)) == 0 for y in range(1, 8))


def test_round_artwork_border_clips_generated_lines(tmp_path):
    original_path = tmp_path / "original.png"
    original = Image.new("RGB", (400, 400), "white")
    draw_original = ImageDraw.Draw(original)
    draw_original.ellipse((45, 35, 355, 345), fill=(181, 132, 72))
    original.save(original_path)

    generated = Image.new("L", (400, 400), 255)
    draw_generated = ImageDraw.Draw(generated)
    draw_generated.line((0, 0, 399, 399), fill=0, width=5)

    restored = _restore_round_border_from_original(generated, str(original_path))

    assert restored.getpixel((5, 5)) == 255
    assert any(restored.getpixel((x, y)) == 0 for x in range(180, 220) for y in range(25, 55))


def test_rounded_page_border_uses_original_shape(tmp_path):
    original_path = tmp_path / "rounded_page.png"
    original = Image.new("RGB", (500, 420), "white")
    draw_original = ImageDraw.Draw(original)
    draw_original.rounded_rectangle((45, 20, 455, 390), radius=95, fill=(168, 124, 82))
    original.save(original_path)

    generated = Image.new("L", (500, 420), 255)
    draw_generated = ImageDraw.Draw(generated)
    draw_generated.line((0, 210, 499, 210), fill=0, width=5)
    draw_generated.line((250, 0, 250, 419), fill=0, width=5)

    restored = _restore_round_border_from_original(generated, str(original_path))

    assert restored.getpixel((5, 210)) == 255
    assert restored.getpixel((250, 5)) == 255
    assert any(restored.getpixel((x, y)) == 0 for x in range(35, 60) for y in range(190, 230))


def test_artwork_mask_ignores_detached_side_color_strip():
    original = Image.new("RGB", (600, 480), "white")
    draw = ImageDraw.Draw(original)
    draw.rounded_rectangle((50, 25, 500, 430), radius=115, fill=(170, 123, 76))
    draw.rectangle((545, 35, 580, 360), fill=(170, 123, 76))

    mask = _detect_artwork_region_mask(original)

    assert mask is not None
    assert mask.getpixel((565, 160)) == 0
    assert mask.getpixel((300, 220)) == 255


def test_create_and_filter_asset():
    resp = client.post("/api/v1/assets/", json={
        "title": "Public domain flower study",
        "source_name": "Internal seed set",
        "source_url": "https://example.com/assets/flower",
        "license_type": "CC0",
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "attribution_text": "CC0 test asset",
        "display_allowed": True,
        "train_allowed": True,
        "commercial_allowed": True,
        "derivative_allowed": True,
        "risk_level": "green",
        "image_url": "/assets/flower.jpg",
        "metadata": {"genre": "flower_bird", "method": "gongbi"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Public domain flower study"
    assert data["risk_level"] == "green"
    assert data["display_allowed"] is True
    assert data["train_allowed"] is True

    list_resp = client.get("/api/v1/assets/?risk_level=green&display_allowed=true")
    assert list_resp.status_code == 200
    assets = list_resp.json()
    assert any(asset["id"] == data["id"] for asset in assets)


def _sample_png_bytes():
    img = Image.new("RGB", (320, 240), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse((70, 40, 180, 150), outline="black", width=4)
    draw.line((180, 130, 250, 210), fill="black", width=4)
    draw.line((115, 150, 92, 220), fill="black", width=3)
    stream = io.BytesIO()
    img.save(stream, format="PNG")
    stream.seek(0)
    return stream.getvalue()


def test_gongbi_line_draft_practice_flow():
    image_bytes = _sample_png_bytes()
    upload_resp = client.post(
        "/api/v1/uploads/reference",
        files={"file": ("flower.png", image_bytes, "image/png")},
        data={"notes": "simple flower"},
    )
    assert upload_resp.status_code == 200
    reference = upload_resp.json()
    assert reference["file_url"].startswith("/uploads/references/")

    draft_resp = client.post("/api/v1/line-drafts/generate", json={
        "reference_upload_id": reference["id"],
        "line_strength": 3,
        "detail_level": 3,
        "preserve_texture": True,
    })
    assert draft_resp.status_code == 200
    draft = draft_resp.json()
    assert draft["file_url"].endswith(".png")
    assert draft["metadata"]["width"] > 0

    session_resp = client.post("/api/v1/practice-sessions/", json={
        "reference_upload_id": reference["id"],
        "line_draft_id": draft["id"],
        "title": "测试工笔花鸟临摹",
    })
    assert session_resp.status_code == 200
    session = session_resp.json()
    assert len(session["steps"]) == 6
    assert session["steps"][0]["title"] == "白描稿与构图定位"

    step_id = session["steps"][0]["id"]
    submission_resp = client.post(
        f"/api/v1/practice-steps/{step_id}/submission",
        files={"file": ("submission.png", image_bytes, "image/png")},
    )
    assert submission_resp.status_code == 200
    step = submission_resp.json()
    assert step["status"] == "review"
    assert step["submission_image_url"].startswith("/uploads/practice_submissions/")
    assert step["overlay_image_url"].startswith("/uploads/overlays/")

    continue_resp = client.post(f"/api/v1/practice-steps/{step_id}/continue")
    assert continue_resp.status_code == 200
    updated_session = continue_resp.json()
    assert updated_session["current_step_num"] == 2


def test_create_artwork():
    resp = client.post("/api/v1/artworks/", json={
        "title": "出水芙蓉图", "genre": "flower_bird",
        "method": "gongbi", "image_url": "/test.jpg",
        "input_method": "photo"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "出水芙蓉图"
    assert data["method"] == "gongbi"
    assert data["genre"] == "flower_bird"
    return data["id"]


def test_list_artworks():
    test_create_artwork()
    resp = client.get("/api/v1/artworks/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_artwork():
    aid = test_create_artwork()
    resp = client.get(f"/api/v1/artworks/{aid}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "出水芙蓉图"


def test_generate_course():
    aid = test_create_artwork()
    resp = client.post("/api/v1/courses/generate?artwork_id=" + aid)
    assert resp.status_code == 200
    data = resp.json()
    assert data["genre"] == "flower_bird"
    assert data["method"] == "gongbi"
    assert len(data["steps"]) == 5
    # 工笔应有 5 步
    assert data["steps"][0]["title"] == "构图定位"
    assert data["steps"][4]["title"] == "复勾调整"
    return data["id"]


def test_get_course():
    aid = test_create_artwork()
    resp = client.post("/api/v1/courses/generate?artwork_id=" + aid)
    cid = resp.json()["id"]
    resp2 = client.get(f"/api/v1/courses/{cid}")
    assert resp2.status_code == 200


def test_submit_and_feedback():
    aid = test_create_artwork()
    course_resp = client.post("/api/v1/courses/generate?artwork_id=" + aid)
    step_id = course_resp.json()["steps"][0]["id"]

    # 提交作业
    sub_resp = client.post("/api/v1/submissions/", json={
        "user_id": "user001", "step_id": step_id,
        "image_url": "/submissions/sub001.jpg"
    })
    assert sub_resp.status_code == 200
    assert sub_resp.json()["status"] == "pending"
    sub_id = sub_resp.json()["id"]

    # 添加反馈
    fb_resp = client.post(f"/api/v1/submissions/{sub_id}/feedback", json={
        "step_id": step_id, "passed": True,
        "overall_comment": "线条匀净，勾线到位",
        "structure_score": 0.85, "stroke_score": 0.90,
        "ink_score": 0.80, "color_score": 0.75, "style_score": 0.82,
        "annotations": []
    })
    assert fb_resp.status_code == 200
    assert fb_resp.json()["status"] == "graded"
    fb = fb_resp.json()["feedback"]
    assert fb["passed"] is True
    assert fb["stroke_score"] == 0.9


def test_write_artwork():
    """写意花鸟测试"""
    resp = client.post("/api/v1/artworks/", json={
        "title": "墨葡萄图", "genre": "flower_bird",
        "method": "xieyi", "image_url": "/test2.jpg",
        "input_method": "search"
    })
    assert resp.status_code == 200
    assert resp.json()["method"] == "xieyi"
    aid = resp.json()["id"]

    course_resp = client.post("/api/v1/courses/generate?artwork_id=" + aid)
    assert course_resp.status_code == 200
    steps = course_resp.json()["steps"]
    # 写意花鸟应有 5 步
    assert len(steps) == 5
    assert steps[1]["title"] == "调色"


if __name__ == "__main__":
    test_health(); print("[PASS] health")
    test_create_artwork(); print("[PASS] create_artwork")
    test_list_artworks(); print("[PASS] list_artworks")
    test_get_artwork(); print("[PASS] get_artwork")
    test_generate_course(); print("[PASS] generate_course (gongbi)")
    test_get_course(); print("[PASS] get_course")
    test_submit_and_feedback(); print("[PASS] submit_and_feedback")
    test_write_artwork(); print("[PASS] xieyi_artwork")
    print("\nAll backend tests PASSED!")
