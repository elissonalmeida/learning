from pathlib import Path
from types import SimpleNamespace
import pytest
import db
import image_gen
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


def make_fake_render(calls=None, overflow=False):
    def build_slide_html(slide_text, image_bytes, brand_pack, slide_role, is_last=False):
        if calls is not None:
            calls.append({"text": slide_text, "image": image_bytes, "role": slide_role, "is_last": is_last})
        return f"<html>{slide_role}:{slide_text}</html>"

    def render_png(html, fit=None):
        if fit is not None:
            fit["overflow"] = overflow
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


def test_generate_slide_image_daily_budget_error_message_is_gentle_pt_pt(conn, idea, tmp_path):
    import tone_guard

    db.log_api_call(conn, "generate_draft", tokens_in=1, tokens_out=1, estimated_cost_usd=2.0, idea_id=idea["id"])
    with pytest.raises(pipeline.DailyBudgetExceededError) as excinfo:
        pipeline.generate_slide_image(
            None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
            image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
        )
    message = str(excinfo.value)
    assert tone_guard.find_harsh_words(message) == []
    assert "$2.00" in message
    assert "This call" not in message


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


def test_generate_slide_image_logs_cost_and_raises_when_gemini_returns_no_image(conn, idea, tmp_path):
    def no_image(client, prompt):
        raise image_gen.NoImageReturned(tokens_in=50, tokens_out=10, cost=0.03)

    fake_image_gen = SimpleNamespace(generate_image=no_image)
    events = []

    with pytest.raises(image_gen.NoImageReturned):
        pipeline.generate_slide_image(
            None, conn, idea, 0, "hero", "texto", "prompt", tmp_path, 2.0,
            image_gen_module=fake_image_gen, render_module=make_fake_render(),
            on_step=lambda step, status, detail=None: events.append((step, status)),
        )

    row = conn.execute("SELECT * FROM api_calls WHERE idea_id = ?", (idea["id"],)).fetchone()
    assert row is not None
    assert row["function"] == "generate_image"
    assert row["estimated_cost_usd"] == pytest.approx(0.03)
    assert events[-1] == ("generate_image", "error")


def test_on_step_reports_error_when_render_fails(conn, idea, tmp_path):
    def failing_render(slide_text, image_bytes, brand_pack, slide_role, is_last=False):
        raise ValueError("contraste insuficiente")

    fake_render = SimpleNamespace(build_slide_html=failing_render, render_png=lambda html, fit=None: b"x")
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


def test_ensure_image_folder_keeps_overlong_saved_folder_that_already_exists(conn, idea, tmp_path):
    legacy = "2026-09-25_" + "b" * 60
    (tmp_path / legacy).mkdir()
    db.set_idea_image_folder(conn, idea["id"], legacy)
    idea = db.get_idea(conn, idea["id"])
    assert pipeline.ensure_image_folder(conn, idea, tmp_path) == legacy


def test_generate_slide_image_keeps_the_raw_image_in_a_raw_subfolder(conn, idea, tmp_path):
    row = pipeline.generate_slide_image(
        None, conn, idea, 3, "card", "texto", "prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
    )
    folder = Path(row["file_path"]).parent
    assert (folder / "_raw" / "slide-03-bg.png").read_bytes() == b"fake-image-bytes"
    assert pipeline.background_path(tmp_path, folder.name, 3) == folder / "_raw" / "slide-03-bg.png"
    # Only publishable slides sit in the carousel folder itself.
    assert sorted(f.name for f in folder.iterdir() if f.is_file()) == ["slide-03.png"]


def test_generate_slide_image_passes_is_last_to_the_layout(conn, idea, tmp_path):
    calls = []
    pipeline.generate_slide_image(
        None, conn, idea, 4, "card", "texto", "prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(calls), is_last=True,
    )
    assert calls[-1]["is_last"] is True


def test_rerender_slide_image_reuses_saved_background_without_any_api_call(conn, idea, tmp_path):
    first = pipeline.generate_slide_image(
        None, conn, idea, 1, "card", "texto antigo", "o prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
    )
    calls_before = conn.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0]
    calls = []

    row = pipeline.rerender_slide_image(
        conn, db.get_idea(conn, idea["id"]), 1, "card", "texto novo", tmp_path, True,
        render_module=make_fake_render(calls),
    )

    assert conn.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0] == calls_before
    assert row["id"] != first["id"]
    assert row["cost_usd"] == 0
    assert row["status"] == "pending"
    assert row["prompt"] == "o prompt"
    assert calls == [{"text": "texto novo", "image": b"fake-image-bytes", "role": "card", "is_last": True}]
    assert Path(row["file_path"]).read_bytes() == b"fake-png-bytes"
    assert len(db.list_slide_images(conn, idea["id"])) == 2


def test_rerender_slide_image_without_saved_background_raises_gentle_error(conn, idea, tmp_path):
    import tone_guard

    with pytest.raises(pipeline.NoSavedBackgroundError) as excinfo:
        pipeline.rerender_slide_image(
            conn, idea, 0, "hero", "texto", tmp_path, False, render_module=make_fake_render(),
        )
    assert tone_guard.find_harsh_words(str(excinfo.value)) == []
    assert db.list_slide_images(conn, idea["id"]) == []


def test_rerender_slide_image_raises_when_folder_exists_but_background_is_missing(conn, idea, tmp_path):
    pipeline.ensure_image_folder(conn, idea, tmp_path)
    with pytest.raises(pipeline.NoSavedBackgroundError):
        pipeline.rerender_slide_image(
            conn, db.get_idea(conn, idea["id"]), 2, "card", "texto", tmp_path, False,
            render_module=make_fake_render(),
        )


def test_rerender_uses_the_prompt_that_produced_the_saved_image(conn, idea, tmp_path):
    pipeline.generate_slide_image(
        None, conn, idea, 1, "card", "texto", "prompt antigo", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
    )
    idea = db.get_idea(conn, idea["id"])

    def failing_render(slide_text, image_bytes, brand_pack, slide_role, is_last=False):
        raise ValueError("falhou a compor")

    with pytest.raises(ValueError):
        pipeline.generate_slide_image(
            None, conn, idea, 1, "card", "texto", "prompt novo", tmp_path, 2.0,
            image_gen_module=make_fake_image_gen(),
            render_module=SimpleNamespace(build_slide_html=failing_render, render_png=None),
        )

    row = pipeline.rerender_slide_image(
        conn, idea, 1, "card", "texto", tmp_path, False, render_module=make_fake_render(),
    )
    assert row["prompt"] == "prompt novo"


@pytest.mark.parametrize("overflow", [True, False])
def test_generate_slide_image_records_text_overflow(conn, idea, tmp_path, overflow):
    row = pipeline.generate_slide_image(
        None, conn, idea, 1, "card", "texto", "prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(overflow=overflow),
    )
    assert bool(row["text_overflow"]) is overflow


def test_rerender_slide_image_records_text_overflow(conn, idea, tmp_path):
    pipeline.generate_slide_image(
        None, conn, idea, 1, "card", "texto", "prompt", tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(),
    )
    row = pipeline.rerender_slide_image(
        conn, db.get_idea(conn, idea["id"]), 1, "card", "texto muito longo", tmp_path, False,
        render_module=make_fake_render(overflow=True),
    )
    assert row["text_overflow"] == 1


# ---- #48: generate several slide images in one go --------------------------

def _jobs(indices, total=4):
    return [(i, "hero" if i == 0 else "card", f"texto {i}", f"prompt {i}", i == total - 1) for i in indices]


def make_scripted_image_gen(outcomes, prompts=None):
    """outcomes maps prompt -> exception to raise; any other prompt succeeds."""
    def generate_image(client, prompt):
        if prompts is not None:
            prompts.append(prompt)
        outcome = outcomes.get(prompt)
        if outcome is not None:
            raise outcome
        return b"fake-image-bytes", 50, 1120, 0.07
    return SimpleNamespace(generate_image=generate_image)


def test_generate_slide_images_makes_every_slide_and_reports_progress(conn, idea, tmp_path):
    calls, progress = [], []
    result = pipeline.generate_slide_images(
        None, conn, idea, _jobs([0, 1, 2, 3]), tmp_path, 2.0,
        image_gen_module=make_fake_image_gen(), render_module=make_fake_render(calls),
        on_progress=lambda position, total, slide_index: progress.append((position, total, slide_index)),
    )
    assert result == {"done": [0, 1, 2, 3], "failed": [], "errors": {}, "not_attempted": [], "budget_message": None}
    assert progress == [(0, 4, 0), (1, 4, 1), (2, 4, 2), (3, 4, 3)]
    assert [c["is_last"] for c in calls] == [False, False, False, True]
    assert [c["role"] for c in calls] == ["hero", "card", "card", "card"]
    latest = db.get_latest_slide_images(conn, idea["id"])
    assert [(r["slide_index"], r["prompt"]) for r in latest] == [(i, f"prompt {i}") for i in range(4)]
    # All slides land in one carousel folder.
    assert len({Path(r["file_path"]).parent for r in latest}) == 1


def test_generate_slide_images_keeps_going_when_one_slide_gets_no_image(conn, idea, tmp_path):
    fake = make_scripted_image_gen({"prompt 1": image_gen.NoImageReturned(tokens_in=5, tokens_out=1, cost=0.03)})
    result = pipeline.generate_slide_images(
        None, conn, idea, _jobs([0, 1, 2]), tmp_path, 2.0,
        image_gen_module=fake, render_module=make_fake_render(),
    )
    assert result["done"] == [0, 2]
    assert result["failed"] == [1]
    assert result["not_attempted"] == []
    assert result["budget_message"] is None
    assert [r["slide_index"] for r in db.get_latest_slide_images(conn, idea["id"])] == [0, 2]
    costs = [r["estimated_cost_usd"] for r in conn.execute("SELECT * FROM api_calls ORDER BY id")]
    assert costs == pytest.approx([0.07, 0.03, 0.07])


def test_generate_slide_images_keeps_going_after_an_unexpected_error(conn, idea, tmp_path):
    fake = make_scripted_image_gen({"prompt 0": RuntimeError("ligação caiu")})
    result = pipeline.generate_slide_images(
        None, conn, idea, _jobs([0, 1]), tmp_path, 2.0,
        image_gen_module=fake, render_module=make_fake_render(),
    )
    assert result["done"] == [1]
    assert result["failed"] == [0]
    assert result["errors"] == {0: "RuntimeError: ligação caiu"}


def test_generate_slide_images_stops_gently_when_the_daily_cap_is_reached(conn, idea, tmp_path):
    import tone_guard

    # 2.0 cap, 1.75 already spent: room for one call at the 0.20 estimate
    # (1.75 + 0.20 <= 2.0); it costs 0.07, then 1.82 + 0.20 > 2.0 stops the rest.
    db.log_api_call(conn, "generate_draft", tokens_in=1, tokens_out=1, estimated_cost_usd=1.75, idea_id=idea["id"])
    prompts = []
    result = pipeline.generate_slide_images(
        None, conn, idea, _jobs([1, 2, 3]), tmp_path, 2.0,
        image_gen_module=make_scripted_image_gen({}, prompts), render_module=make_fake_render(),
    )
    assert result["done"] == [1]
    assert result["failed"] == []
    assert result["not_attempted"] == [2, 3]
    assert "$2.00" in result["budget_message"]
    assert tone_guard.find_harsh_words(result["budget_message"]) == []
    assert prompts == ["prompt 1"]  # nothing is sent once the cap would be passed
    assert db.get_spend_today(conn) == pytest.approx(1.82)  # the attempted image is logged
