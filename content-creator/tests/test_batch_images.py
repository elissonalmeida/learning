"""#48: "Gerar todas as imagens", "Recriar todas" and the per-slide "Recriar"."""
import base64
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import db
import image_gen
import render
import tone_guard

APP_PATH = str(Path(__file__).parent.parent / "app.py")

_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY"
    "42YAAAAASUVORK5CYII="
)


def _setup(tmp_path, monkeypatch, with_images=(), approved=(), spent=0.0):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")
    monkeypatch.setenv("MAX_DAILY_SPEND_USD", "2.0")

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    db.update_idea_status(conn, idea_id, "approved")
    db.create_draft(conn, idea_id, 0, "Legenda", ["Slide 1", "Slide 2", "Slide 3"])
    for k in with_images:
        path = tmp_path / f"old-{k}.png"
        path.write_bytes(_TINY_PNG_BYTES)
        image_id = db.create_slide_image(conn, idea_id, k, f"prompt guardado {k}", str(path), 0.05)
        if k in approved:
            db.update_slide_image_status(conn, image_id, "approved")
    if spent:
        db.log_api_call(conn, "generate_draft", 1, 1, spent, idea_id=idea_id)
    conn.close()
    return db_path, idea_id


def _fake_gemini(monkeypatch, fail_prompts=()):
    """Records each prompt sent; prompts containing any of fail_prompts get
    no image back."""
    sent = []

    def generate_image(client, prompt):
        sent.append(prompt)
        if any(p in prompt for p in fail_prompts):
            raise image_gen.NoImageReturned(tokens_in=1, tokens_out=1, cost=0.01)
        return _TINY_PNG_BYTES, 1, 1, 0.05

    monkeypatch.setattr(image_gen, "generate_image", generate_image)
    monkeypatch.setattr(render, "build_slide_html", lambda text, image, brand, role, is_last=False: "<html></html>")
    monkeypatch.setattr(render, "render_png", lambda html, fit=None: _TINY_PNG_BYTES)
    return sent


def _latest(db_path, idea_id):
    conn = db.get_connection(str(db_path))
    rows = {r["slide_index"]: dict(r) for r in db.get_latest_slide_images(conn, idea_id)}
    conn.close()
    return rows


def _labels(at):
    return [b.label for b in at.button]


def _texts(at):
    return (
        [e.value for e in at.info] + [e.value for e in at.warning] + [e.value for e in at.success]
        + [e.value for e in at.caption] + _labels(at)
    )


def _assert_gentle(at):
    for text in _texts(at):
        assert tone_guard.find_harsh_words(text) == [], text


def _app():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def test_gerar_todas_shows_only_when_a_slide_has_no_image_with_its_upper_bound_cost(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, with_images=[0])
    at = _app()

    assert "Gerar todas as imagens" in _labels(at)
    assert any("2 imagens — até cerca de $0.40" in c.value for c in at.caption)
    _assert_gentle(at)


def test_with_every_image_made_only_recriar_todas_and_per_slide_recriar_show(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, with_images=[0, 1, 2])
    at = _app()

    labels = _labels(at)
    assert "Gerar todas as imagens" not in labels
    assert "Recriar todas" in labels
    assert "Gerar novamente" not in labels
    assert [b.key for b in at.button if b.label == "Recriar"] == ["regen_0", "regen_1", "regen_2"]


def test_without_any_image_recriar_todas_is_not_offered(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    at = _app()

    assert "Recriar todas" not in _labels(at)
    assert "Gerar todas as imagens" in _labels(at)


def test_per_slide_recriar_still_opens_the_editable_prompt(tmp_path, monkeypatch):
    _, idea_id = _setup(tmp_path, monkeypatch, with_images=[0, 1, 2])
    at = _app()

    [b for b in at.button if b.label == "Recriar" and b.key == "regen_1"][0].click().run()

    assert not at.exception
    assert at.text_area(key=f"prompt_area_{idea_id}_1")
    assert at.button(key="generate_1")


def test_recriar_todas_prefers_an_edited_prompt_over_the_saved_one(tmp_path, monkeypatch):
    db_path, idea_id = _setup(tmp_path, monkeypatch, with_images=[0, 1, 2])
    sent = _fake_gemini(monkeypatch)
    at = _app()
    at.button(key="regen_1").click().run()
    at.text_area(key=f"prompt_area_{idea_id}_1").set_value("prompt novo do slide 2").run()

    at.button(key="recreate_all").click().run()
    at.button(key="recreate_all_yes").click().run()

    assert not at.exception
    assert sent == ["prompt guardado 0", "prompt novo do slide 2", "prompt guardado 2"]


def test_gerar_todas_makes_only_the_missing_slides(tmp_path, monkeypatch):
    db_path, idea_id = _setup(tmp_path, monkeypatch, with_images=[0], approved=[0])
    sent = _fake_gemini(monkeypatch)
    at = _app()

    at.button(key="generate_all").click().run()

    assert not at.exception
    assert len(sent) == 2
    latest = _latest(db_path, idea_id)
    assert latest[0]["prompt"] == "prompt guardado 0" and latest[0]["status"] == "approved"
    assert latest[1]["status"] == latest[2]["status"] == "pending"
    assert any("2 imagens novas prontas" in s.value for s in at.success)
    assert "Gerar todas as imagens" not in _labels(at)
    _assert_gentle(at)


def test_gerar_todas_uses_the_prompt_the_user_edited(tmp_path, monkeypatch):
    db_path, idea_id = _setup(tmp_path, monkeypatch, with_images=[0])
    sent = _fake_gemini(monkeypatch)
    at = _app()
    at.text_area(key=f"prompt_area_{idea_id}_2").set_value("o meu prompt editado").run()

    at.button(key="generate_all").click().run()

    assert not at.exception
    assert _latest(db_path, idea_id)[2]["prompt"] == "o meu prompt editado"
    assert "o meu prompt editado" in sent


def test_recriar_todas_asks_first_and_cancelar_changes_nothing(tmp_path, monkeypatch):
    db_path, idea_id = _setup(tmp_path, monkeypatch, with_images=[0, 1, 2], approved=[0, 1, 2])
    sent = _fake_gemini(monkeypatch)
    at = _app()

    at.button(key="recreate_all").click().run()

    assert not at.exception
    assert sent == []
    assert any("também para os que já aprovaste" in w.value for w in at.warning)
    assert any("3 imagens — até cerca de $0.60" in w.value for w in at.warning)
    assert "Sim, recriar todas" in _labels(at)
    _assert_gentle(at)

    at.button(key="recreate_all_cancel").click().run()

    assert not at.exception
    assert sent == []
    assert not at.warning
    assert "Sim, recriar todas" not in _labels(at)


def test_recriar_todas_after_confirming_remakes_every_slide_with_its_saved_prompt(tmp_path, monkeypatch):
    db_path, idea_id = _setup(tmp_path, monkeypatch, with_images=[0, 1, 2], approved=[0, 1, 2])
    sent = _fake_gemini(monkeypatch)
    at = _app()
    at.button(key="recreate_all").click().run()

    at.button(key="recreate_all_yes").click().run()

    assert not at.exception
    assert sent == ["prompt guardado 0", "prompt guardado 1", "prompt guardado 2"]
    latest = _latest(db_path, idea_id)
    assert [latest[k]["status"] for k in range(3)] == ["pending"] * 3
    assert all(latest[k]["file_path"] != str(tmp_path / f"old-{k}.png") for k in range(3))
    assert not at.warning


def test_failed_slides_are_named_and_can_be_retried_on_their_own(tmp_path, monkeypatch):
    db_path, idea_id = _setup(tmp_path, monkeypatch, with_images=[0, 1, 2])
    sent = _fake_gemini(monkeypatch, fail_prompts=["guardado 1", "guardado 2"])
    at = _app()
    at.button(key="recreate_all").click().run()
    at.button(key="recreate_all_yes").click().run()

    assert not at.exception
    assert len(sent) == 3
    assert any("Slide 2, Slide 3" in i.value for i in at.info)
    assert any("1 imagem nova pronta" in s.value for s in at.success)
    _assert_gentle(at)

    sent = _fake_gemini(monkeypatch)  # works this time
    at.button(key="retry_failed").click().run()

    assert not at.exception
    assert sent == ["prompt guardado 1", "prompt guardado 2"]
    assert "Tentar de novo só estas" not in _labels(at)
    assert any("2 imagens novas prontas" in s.value for s in at.success)


def test_budget_heads_up_before_and_gentle_stop_during_the_batch(tmp_path, monkeypatch):
    # $2.00 cap, $1.76 spent: at the $0.20 estimate one image fits (1.76 + 0.20 <= 2.00);
    # it costs $0.05, then 1.81 + 0.20 > 2.00 stops the rest.
    db_path, idea_id = _setup(tmp_path, monkeypatch, spent=1.76)
    sent = _fake_gemini(monkeypatch)
    at = _app()

    assert any("deve chegar para cerca de 1" in c.value for c in at.caption)
    _assert_gentle(at)

    at.button(key="generate_all").click().run()

    assert not at.exception
    assert len(sent) == 1
    assert list(_latest(db_path, idea_id)) == [0]
    assert any("limite de gastos" in i.value and "Ficaram para depois: Slide 2, Slide 3" in i.value for i in at.info)
    assert not [e for e in at.error]
    _assert_gentle(at)
