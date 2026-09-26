"""#47 (enlarged slide view with an obvious way back) and #49 (Instagram-like
carousel preview)."""
import base64
import re
from pathlib import Path

from streamlit.testing.v1 import AppTest

import db

APP_PATH = str(Path(__file__).parent.parent / "app.py")

_TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY"
    "42YAAAAASUVORK5CYII="
)
LONG_CAPTION = (
    "Há manhãs em que o corpo pede calma antes de tudo. Um chá quente, três respirações "
    "e a janela aberta chegam para começar o dia com outra leveza. FIM-DA-LEGENDA"
)


def _slide_bytes(index):
    # Same tiny PNG, plus a per-slide trailer (ignored by decoders) so each
    # slide's data URI is distinguishable.
    return _TINY_PNG_BYTES + f"slide-{index}".encode()


def _uri(index):
    return "data:image/png;base64," + base64.b64encode(_slide_bytes(index)).decode()


def _setup(tmp_path, monkeypatch, approve=True, n_slides=3, extra_idea=False):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gk-test-not-real")
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("BRAND_PACK", "marianabotelho-ig")

    conn = db.get_connection(str(db_path))
    db.init_db(conn)
    if extra_idea:
        other = db.create_idea(conn, "marianabotelho-ig", "manual", "outra ideia")
        db.update_idea_status(conn, other, "approved")
        db.create_draft(conn, other, 0, "Outra", ["Outro slide"])
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    db.create_draft(conn, idea_id, 0, LONG_CAPTION, [f"Slide {k + 1}" for k in range(n_slides)])
    for k in range(n_slides):
        path = tmp_path / f"slide-{k:02d}.png"
        path.write_bytes(_slide_bytes(k))
        image_id = db.create_slide_image(conn, idea_id, k, f"prompt {k}", str(path), 0.05)
        if approve:
            db.update_slide_image_status(conn, image_id, "approved")
    db.update_idea_status(conn, idea_id, "images_ready" if approve else "approved")
    conn.close()
    return idea_id


def _htmls(at):
    return [el.proto.body for el in at.get("html")]


def _enlarged(at):
    return [h for h in _htmls(at) if "enlarged-slide" in h]


def _post(at):
    posts = [h for h in _htmls(at) if "ig-post" in h]
    assert len(posts) == 1
    return posts[0]


def _button(at, label=None, key=None):
    matches = [b for b in at.button if (label is None or b.label == label) and (key is None or b.key == key)]
    assert matches, f"no button {label!r}/{key!r}"
    return matches[0]


# ---- #47: "Ver maior" dialog ----------------------------------------------

def test_each_slide_with_an_image_has_a_ver_maior_button(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, approve=False)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    assert not at.exception
    assert [b.key for b in at.button if b.label == "Ver maior"] == ["enlarge_0", "enlarge_1", "enlarge_2"]
    assert not _enlarged(at)


def test_ver_maior_opens_the_slide_big_with_fechar_and_fechar_closes_it(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, approve=False)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    _button(at, key="enlarge_1").click().run()

    assert not at.exception
    shown = _enlarged(at)
    assert len(shown) == 1 and _uri(1) in shown[0]
    assert any("Slide 2 de 3" in c.value for c in at.caption)
    assert _button(at, label="Fechar")

    _button(at, label="Fechar").click().run()

    assert not at.exception
    assert not _enlarged(at)
    assert not [b for b in at.button if b.label == "Fechar"]


def test_anterior_and_seguinte_inside_the_dialog_change_the_slide(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, approve=False)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _button(at, key="enlarge_1").click().run()

    _button(at, key="enlarged_next").click().run()
    assert _uri(2) in _enlarged(at)[0]
    assert _button(at, key="enlarged_next").disabled

    _button(at, key="enlarged_prev").click().run()
    _button(at, key="enlarged_prev").click().run()
    assert _uri(0) in _enlarged(at)[0]
    assert _button(at, key="enlarged_prev").disabled
    assert any("Slide 1 de 3" in c.value for c in at.caption)


def test_closing_the_dialog_keeps_the_selected_idea(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, approve=False, extra_idea=True)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    select = at.selectbox(key="img_idea_select")
    ritual = [o for o in select.options if "ritual matinal" in o][0]
    select.set_value(ritual).run()

    _button(at, key="enlarge_0").click().run()
    _button(at, label="Fechar").click().run()

    assert not at.exception
    assert at.selectbox(key="img_idea_select").value == ritual
    assert [b.key for b in at.button if b.label == "Ver maior"] == ["enlarge_0", "enlarge_1", "enlarge_2"]


def test_theme_hides_the_builtin_fullscreen_button_only_on_images():
    import theme

    assert '[data-testid="stElementToolbar"]' in theme.HEADER_CSS
    assert ':has([data-testid="stImage"])' in theme.HEADER_CSS


# ---- #49: Instagram-like preview -------------------------------------------

def test_preview_looks_like_an_instagram_post(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    assert not at.exception
    post = _post(at)
    assert '<span class="ig-handle">marianabotelho.pt</span>' in post  # Handle from the brand pack
    assert "<b>marianabotelho.pt</b>" in post  # bold handle before the caption
    assert "1/3" in post
    assert post.count('class="ig-dot"') + post.count('class="ig-dot active"') == 3
    assert post.index('class="ig-dot active"') < post.index('class="ig-dot"')
    assert _uri(0) in post
    assert '… <span class="ig-mais">mais</span>' in post
    assert "FIM-DA-LEGENDA" not in post


def test_switching_slide_updates_the_counter_and_the_dot(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    _button(at, label="Seguinte ▶").click().run()

    post = _post(at)
    assert "2/3" in post
    assert re.findall(r'class="ig-dot( active)?"', post) == ["", " active", ""]
    assert _uri(1) in post

    _button(at, key="thumb_2").click().run()
    assert "3/3" in _post(at)


def test_ver_legenda_completa_shows_the_whole_caption(tmp_path, monkeypatch):
    idea_id = _setup(tmp_path, monkeypatch)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    at.toggle(key=f"full_caption_{idea_id}").set_value(True).run()

    post = _post(at)
    assert "FIM-DA-LEGENDA" in post
    assert '<span class="ig-mais">' not in post


def test_preview_ver_maior_opens_the_current_slide(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _button(at, label="Seguinte ▶").click().run()

    _button(at, key="enlarge_preview").click().run()

    assert not at.exception
    assert _uri(1) in _enlarged(at)[0]


def test_preview_waits_gently_until_all_slides_are_approved(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, approve=False)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    assert not [h for h in _htmls(at) if "ig-post" in h]
    assert any("Aprova todas as imagens" in i.value for i in at.info)


def test_avatar_from_the_brand_pack_or_the_handle_initial():
    import ig_preview

    with_avatar = ig_preview.post_html("data:image/png;base64,AA", "@marca", "data:image/png;base64,AV", 0, 2, "Olá")
    assert '<div class="ig-avatar"><img src="data:image/png;base64,AV"' in with_avatar
    without = ig_preview.post_html("data:image/png;base64,AA", "@marca", None, 0, 2, "Olá")
    assert '<div class="ig-avatar">M</div>' in without
    assert '<span class="ig-mais">' not in without  # short caption is not cut


def test_full_caption_toggle_is_per_idea(tmp_path, monkeypatch):
    first = _setup(tmp_path, monkeypatch)
    second = _setup(tmp_path, monkeypatch)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    select = at.selectbox(key="img_idea_select")
    label_a = [o for o in select.options if o.startswith(f"#{first} ")][0]
    label_b = [o for o in select.options if o.startswith(f"#{second} ")][0]
    select.set_value(label_a).run()
    [t for t in at.toggle if t.label == "Ver legenda completa"][0].set_value(True).run()
    assert "FIM-DA-LEGENDA" in _post(at)

    at.selectbox(key="img_idea_select").set_value(label_b).run()

    assert not at.exception
    post = _post(at)
    assert "FIM-DA-LEGENDA" not in post
    assert '<span class="ig-mais">' in post
