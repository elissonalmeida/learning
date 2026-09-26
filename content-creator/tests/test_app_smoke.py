import base64
from pathlib import Path

import pytest
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

    at = AppTest.from_file(APP_PATH, default_timeout=30)
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

    at = AppTest.from_file(APP_PATH, default_timeout=30)
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
    at = AppTest.from_file(APP_PATH, default_timeout=30)
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

    # The draft section closes and the idea leaves the "reviewed" list right
    # away, in the same interaction (no second click needed).
    assert not [b for b in at.button if b.key == f"approve_draft_{idea_id}"]
    assert any("Sem rascunhos à espera de decisão" in el.value for el in at.info)


def test_generating_a_draft_selects_it_in_the_reviewed_section(tmp_path, monkeypatch):
    import ai

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    # The idea we're about to draft was created FIRST (older created_at); a
    # second idea, created and marked "reviewed" AFTER it, has a newer
    # created_at. list_ideas() sorts "reviewed" by created_at DESC, so once
    # the first idea also becomes "reviewed", plain creation-time sorting
    # would still put the older one second — the selectbox must not rely on
    # that sort order to find the just-generated draft.
    new_idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ideia nova")
    old_idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ideia antiga")
    db.update_idea_status(conn, old_idea_id, "reviewed")
    db.create_draft(conn, old_idea_id, 0, "Legenda antiga", ["Slide antigo"])
    conn.close()

    monkeypatch.setattr(
        ai, "generate_draft",
        lambda client, topic, tone, pillar, brand_pack: (
            {"caption": "Legenda nova", "slides": ["Slide novo"]}, 10, 10, 0.001,
        ),
    )
    monkeypatch.setattr(
        ai, "critique_draft", lambda client, draft, brand_pack: ([], 10, 10, 0.001),
    )

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    gerar_buttons = [b for b in at.button if b.label == "Gerar rascunho"]
    assert len(gerar_buttons) == 1
    gerar_buttons[0].click().run()

    assert not at.exception
    reviewed_select = at.selectbox(key="reviewed_idea_select")
    assert reviewed_select.value == f"#{new_idea_id} — ideia nova"

    # The review section renders the caption verbatim (st.write(caption));
    # the Biblioteca tab renders "Ronda N: <caption>..." — exclude that so
    # this only looks at what the review section is showing.
    review_section_captions = [
        el.value for el in at.markdown
        if "Ronda" not in el.value and ("Legenda nova" in el.value or "Legenda antiga" in el.value)
    ]
    assert any("Legenda nova" in v for v in review_section_captions)
    assert not any("Legenda antiga" in v for v in review_section_captions)

    aprovar_buttons = [b for b in at.button if b.key == f"approve_draft_{new_idea_id}"]
    assert len(aprovar_buttons) == 1
    aprovar_buttons[0].click().run()

    conn2 = db.get_connection(str(db_path))
    assert db.get_idea(conn2, new_idea_id)["status"] == "approved"
    assert db.get_idea(conn2, old_idea_id)["status"] == "reviewed"
    conn2.close()


def test_arquivar_hides_the_button_in_the_same_interaction(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    conn.close()

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    at.button(key=f"archive_{idea_id}").click().run()

    assert not at.exception
    archive_buttons = [b for b in at.button if b.key == f"archive_{idea_id}"]
    assert archive_buttons == []


def test_no_image_returned_shows_gentle_message_and_keeps_prompt_editable(tmp_path, monkeypatch):
    import image_gen

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

    def no_image(client, prompt):
        raise image_gen.NoImageReturned(tokens_in=50, tokens_out=10, cost=0.03)

    monkeypatch.setattr(image_gen, "generate_image", no_image)

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    at.button(key="generate_0").click().run()

    assert not at.exception
    assert any(
        "Desta vez não veio imagem" in w.value for w in at.warning
    )
    assert not [e for e in at.error if "Desta vez não veio imagem" in e.value]
    # The prompt textarea must still be there to edit and retry.
    assert at.text_area(key="prompt_area_1_0")
    # A missing image is an expected outcome, not a failure: the status
    # label/state must not read like a crash.
    status = at.status[-1]
    assert status.label != "Falhou"
    assert status.state != "error"

    conn2 = db.get_connection(str(db_path))
    row = conn2.execute("SELECT * FROM api_calls WHERE idea_id = ?", (idea_id,)).fetchone()
    assert row is not None
    assert row["estimated_cost_usd"] == pytest.approx(0.03)
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

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    assert not at.exception


def _idea_with_two_slide_images(tmp_path, monkeypatch, with_background_for):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    folder = tmp_path / "images" / "2026-09-26_ritual"
    folder.mkdir(parents=True)
    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    db.update_idea_status(conn, idea_id, "approved")
    db.set_idea_image_folder(conn, idea_id, folder.name)
    db.create_draft(conn, idea_id, 0, "Legenda de teste", ["Slide 1", "Slide 2"])
    for index in (0, 1):
        slide = folder / f"slide-{index:02d}.png"
        slide.write_bytes(_TINY_PNG_BYTES)
        db.create_slide_image(conn, idea_id, index, f"prompt {index}", str(slide), 0.05)
    for index in with_background_for:
        (folder / f"slide-{index:02d}-bg.png").write_bytes(_TINY_PNG_BYTES)
    conn.close()
    return db_path, idea_id


def test_refazer_layout_appears_only_when_the_raw_image_was_saved(tmp_path, monkeypatch):
    _idea_with_two_slide_images(tmp_path, monkeypatch, with_background_for=[0])

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    assert not at.exception
    rerender = [b for b in at.button if b.label == "Refazer layout"]
    assert [b.key for b in rerender] == ["rerender_0"]


def test_refazer_layout_adds_a_free_new_version_of_the_last_slide(tmp_path, monkeypatch):
    import render

    db_path, idea_id = _idea_with_two_slide_images(tmp_path, monkeypatch, with_background_for=[1])
    layouts = []
    monkeypatch.setattr(
        render, "build_slide_html",
        lambda text, image, brand, role, is_last=False: layouts.append((role, is_last)) or "<html></html>",
    )
    monkeypatch.setattr(render, "render_png", lambda html: _TINY_PNG_BYTES)

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.button(key="rerender_1").click().run()

    assert not at.exception
    assert layouts == [("card", True)]
    conn = db.get_connection(str(db_path))
    rows = [r for r in db.list_slide_images(conn, idea_id) if r["slide_index"] == 1]
    assert len(rows) == 2
    assert rows[-1]["cost_usd"] == 0
    assert conn.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0] == 0
    conn.close()


def test_gerar_imagem_tells_the_layout_which_slide_is_the_last(tmp_path, monkeypatch):
    import image_gen
    import render

    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")
    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    db.update_idea_status(conn, idea_id, "approved")
    db.create_draft(conn, idea_id, 0, "Legenda de teste", ["Slide 1", "Slide 2", "Slide 3"])
    conn.close()

    layouts = []
    monkeypatch.setattr(image_gen, "generate_image", lambda client, prompt: (_TINY_PNG_BYTES, 1, 1, 0.01))
    monkeypatch.setattr(
        render, "build_slide_html",
        lambda text, image, brand, role, is_last=False: layouts.append((text, is_last)) or "<html></html>",
    )
    monkeypatch.setattr(render, "render_png", lambda html: _TINY_PNG_BYTES)

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.button(key="generate_1").click().run()
    at.button(key="generate_2").click().run()

    assert not at.exception
    assert layouts == [("Slide 2", False), ("Slide 3", True)]
