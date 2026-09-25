from pathlib import Path
from types import SimpleNamespace
import pytest
import db
import pipeline


@pytest.fixture
def conn():
    connection = db.get_connection(":memory:")
    db.init_db(connection)
    return connection


@pytest.fixture
def idea(conn):
    idea_id = db.create_idea(conn, "marianabotelho-ig", "manual", "ritual matinal")
    return db.get_idea(conn, idea_id)


def make_fake_image_gen(cost=0.07):
    def generate_image(client, prompt):
        return b"fake-image-bytes", 50, 1120, cost
    return SimpleNamespace(generate_image=generate_image)


def make_fake_render():
    def build_slide_html(slide_text, image_bytes, brand_pack, slide_role):
        return f"<html>{slide_role}:{slide_text}</html>"

    def render_png(html):
        return b"fake-png-bytes"

    return SimpleNamespace(build_slide_html=build_slide_html, render_png=render_png)


def test_generate_slide_image_creates_file_and_db_row(conn, idea, tmp_path):
    row = pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "Ritual matinal", "um prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
    )
    assert row["status"] == "pending"
    assert row["cost_usd"] == pytest.approx(0.07)
    saved_file = Path(row["file_path"])
    assert saved_file.exists()
    assert saved_file.read_bytes() == b"fake-png-bytes"


def test_generate_slide_image_sets_and_reuses_image_folder(conn, idea, tmp_path):
    fake_image_gen = make_fake_image_gen()
    fake_render = make_fake_render()
    row1 = pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    idea_after = db.get_idea(conn, idea["id"])
    assert idea_after["image_folder"] is not None

    row2 = pipeline.generate_slide_image(
        None, conn, idea_after, 1, "card", "texto 2", "prompt 2", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    assert Path(row1["file_path"]).parent == Path(row2["file_path"]).parent


def test_generate_slide_image_raises_when_daily_cap_already_reached(conn, idea, tmp_path):
    db.log_api_call(conn, "generate_draft", tokens_in=1, tokens_out=1, estimated_cost_usd=2.0, idea_id=idea["id"])
    with pytest.raises(pipeline.DailyBudgetExceededError):
        pipeline.generate_slide_image(
            None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
            image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
        )


def test_generate_slide_image_reports_progress_via_on_step(conn, idea, tmp_path):
    events = []
    pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
        on_step=lambda step, status, detail=None: events.append((step, status)),
    )
    assert events == [
        ("generate_image", "running"), ("generate_image", "done"),
        ("render_image", "running"), ("render_image", "done"),
    ]


def test_on_step_reports_error_when_render_fails(conn, idea, tmp_path):
    def failing_render(slide_text, image_bytes, brand_pack, slide_role):
        raise ValueError("contraste insuficiente")

    fake_render = SimpleNamespace(build_slide_html=failing_render, render_png=lambda html: b"x")
    events = []
    with pytest.raises(ValueError):
        pipeline.generate_slide_image(
            None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
            image_gen_module=make_fake_image_gen(), render_module=fake_render,
            on_step=lambda step, status, detail=None: events.append((step, status, detail)),
        )
    assert events[-1] == ("render_image", "error", "contraste insuficiente")


def test_regenerating_a_slide_creates_a_new_row_not_overwrite(conn, idea, tmp_path):
    fake_image_gen = make_fake_image_gen()
    fake_render = make_fake_render()
    row1 = pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "texto", "prompt v1", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    idea_after = db.get_idea(conn, idea["id"])
    row2 = pipeline.generate_slide_image(
        None, conn, idea_after, 0, "hero", "texto", "prompt v2", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    assert row1["id"] != row2["id"]
    assert len(db.list_slide_images(conn, idea["id"])) == 2


def test_approve_and_reject_slide_image(conn, idea, tmp_path):
    row = pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
    )
    pipeline.approve_slide_image(conn, row["id"])
    assert db.get_slide_image(conn, row["id"])["status"] == "approved"
    pipeline.reject_slide_image(conn, row["id"])
    assert db.get_slide_image(conn, row["id"])["status"] == "rejected"


def test_maybe_mark_images_ready_only_when_all_slides_approved(conn, idea, tmp_path):
    fake_image_gen = make_fake_image_gen()
    fake_render = make_fake_render()
    row0 = pipeline.generate_slide_image(
        None, conn, idea, 0, "hero", "t0", "p0", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    idea_after = db.get_idea(conn, idea["id"])
    row1 = pipeline.generate_slide_image(
        None, conn, idea_after, 1, "card", "t1", "p1", tmp_path, 2.0,
        image_gen_module=fake_image_gen, render_module=fake_render,
    )
    pipeline.approve_slide_image(conn, row0["id"])
    pipeline.maybe_mark_images_ready(conn, idea["id"], total_slides=2)
    assert db.get_idea(conn, idea["id"])["status"] != "images_ready"

    pipeline.approve_slide_image(conn, row1["id"])
    pipeline.maybe_mark_images_ready(conn, idea["id"], total_slides=2)
    assert db.get_idea(conn, idea["id"])["status"] == "images_ready"


def test_ensure_image_folder_replaces_overlong_saved_folder(conn, idea, tmp_path):
    long_name = "2026-09-25_" + "a" * 250
    db.set_idea_image_folder(conn, idea["id"], long_name)
    idea = db.get_idea(conn, idea["id"])
    folder = pipeline.ensure_image_folder(conn, idea, tmp_path)
    assert folder != long_name
    assert len(folder) <= 70
    assert (tmp_path / folder).is_dir()
    assert db.get_idea(conn, idea["id"])["image_folder"] == folder
