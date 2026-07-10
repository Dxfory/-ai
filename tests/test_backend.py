"""backend API 测试 (使用 TestClient)"""

import io
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from backend.app import app
from backend.database import init_db
from backend.services.line_draft import BAIMIAO_PROMPT, _resolve_image_size, _restore_round_border_from_original

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
    assert "任何花、叶、枝、鸟、线条都不得越过边界外侧" in BAIMIAO_PROMPT
    assert "补全必要结构线" not in BAIMIAO_PROMPT
    assert "鸟体等" not in BAIMIAO_PROMPT


def test_baimiao_auto_size_resolves_to_supported_size(tmp_path, monkeypatch):
    monkeypatch.setenv("BAIMIAO_IMAGE_SIZE", "auto")
    image_path = tmp_path / "wide.png"
    Image.new("RGB", (1200, 800), "white").save(image_path)

    assert _resolve_image_size(str(image_path)) == "1536x1024"


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
