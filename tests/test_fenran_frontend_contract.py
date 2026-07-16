from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_exposes_staged_fenran_controls_and_registration_editor():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert 'id="includeBaseColor"' in html
    assert 'id="forceFenranRegenerate"' in html
    assert 'id="registrationArea"' in html
    assert "renderFenranStages(state.fenran)" in app
    assert "fenran.stages" in app
    assert "stage.validation" in app
    assert "stage.pigments" in app
    assert "include_base_color" in app
    assert "force_regenerate" in app
    assert "completed_stages" in app
    assert "review_required" in app


def test_frontend_stage_images_use_intrinsic_ratio_without_fixed_three_panel_template():
    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

    assert "height: auto" in css
    assert "object-fit: contain" in css
    assert "fenran-stages" in css
