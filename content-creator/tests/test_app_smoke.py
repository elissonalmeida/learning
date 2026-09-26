import base64
from pathlib import Path
from streamlit.testing.v1 import AppTest

import db

APP_PATH = str(Path(__file__).parent.parent / "app.py")

# Minimal valid 1x1 transparent PNG, used as a real (tiny) placeholder image
# file so st.image() has something real to load instead of erroring.
_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY"
    "42YAAAAASUVORK5CYII="
)


def test_app_loads_without_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    at = AppTest.from_file(APP_PATH)
    at.run()

    assert not at.exception


def test_images_tab_renders_for_approved_idea_with_draft(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    db.update_idea_status(conn, idea_id, "approved")
    db.create_draft(conn, idea_id, 0, "Legenda de teste", ["Slide 1", "Slide 2"])
    conn.close()

    at = AppTest.from_file(APP_PATH)
    at.run()

    assert not at.exception


def test_reviewed_draft_survives_reload_and_aprovar_updates_status(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    db.update_idea_status(conn, idea_id, "reviewed")
    db.create_draft(
        conn, idea_id, 0, "Legenda de teste", ["Slide 1", "Slide 2"],
        quality_flags=[{"criterion": "Hook", "issue": "fraco"}],
    )
    conn.close()

    # Fresh AppTest run (simulates a reload): no session state carried over.
    at = AppTest.from_file(APP_PATH)
    at.run()

    assert not at.exception
    caption_blocks = [el.value for el in at.markdown if "Legenda de teste" in el.value]
    assert caption_blocks or any("Legenda de teste" in w.value for w in at.text)

    aprovar_buttons = [b for b in at.button if b.label == "Aprovar"]
    assert len(aprovar_buttons) == 1
    aprovar_buttons[0].click().run()

    assert not at.exception
    conn2 = db.get_connection(str(db_path))
    assert db.get_idea(conn2, idea_id)["status"] == "approved"
    conn2.close()


def test_carousel_preview_renders_when_all_slides_approved(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    slide_1 = tmp_path / "slide-00.png"
    slide_2 = tmp_path / "slide-01.png"
    slide_1.write_bytes(_TINY_PNG_BYTES)
    slide_2.write_bytes(_TINY_PNG_BYTES)

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    db.create_draft(conn, idea_id, 0, "Legenda de teste", ["Slide 1", "Slide 2"])
    img1_id = db.create_slide_image(conn, idea_id, 0, "prompt 1", str(slide_1), 0.05)
    img2_id = db.create_slide_image(conn, idea_id, 1, "prompt 2", str(slide_2), 0.05)
    db.update_slide_image_status(conn, img1_id, "approved")
    db.update_slide_image_status(conn, img2_id, "approved")
    db.update_idea_status(conn, idea_id, "images_ready")
    conn.close()

    at = AppTest.from_file(APP_PATH)
    at.run()

    assert not at.exception
