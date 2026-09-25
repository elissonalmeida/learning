from datetime import datetime, timezone
from pathlib import Path

import ai
import db
import image_gen
import render
import storage

ESTIMATED_MAX_CALL_COST_USD = 0.20


class DailyBudgetExceededError(Exception):
    pass


def _invoke(conn, idea_id, daily_cap_usd, function_name, ai_call, on_step=None):
    if on_step:
        on_step(function_name, "running")

    if db.would_exceed_daily_cap(conn, ESTIMATED_MAX_CALL_COST_USD, daily_cap_usd):
        error = DailyBudgetExceededError(
            f"This call could push today's spend over the ${daily_cap_usd:.2f} daily cap. "
            "Try again tomorrow or raise MAX_DAILY_SPEND_USD."
        )
        if on_step:
            on_step(function_name, "error", str(error))
        raise error

    try:
        result, tokens_in, tokens_out, cost = ai_call()
    except Exception as e:
        if on_step:
            on_step(function_name, "error", str(e))
        raise

    db.log_api_call(conn, function_name, tokens_in, tokens_out, cost, idea_id=idea_id)
    if on_step:
        on_step(function_name, "done")
    return result


def run_extraction(client, conn, reference_text, brand_pack, daily_cap_usd, ai_module=ai, on_step=None):
    return _invoke(
        conn, None, daily_cap_usd, "extract_topics",
        lambda: ai_module.extract_topics(client, reference_text, brand_pack),
        on_step=on_step,
    )


def run_generation_pipeline(client, conn, idea, tone, brand_pack, daily_cap_usd, ai_module=ai, on_step=None):
    idea_id = idea["id"]

    draft = _invoke(
        conn, idea_id, daily_cap_usd, "generate_draft",
        lambda: ai_module.generate_draft(client, idea["topic"], tone, idea["pillar"], brand_pack),
        on_step=on_step,
    )
    round_ = 0
    # Persist the paid-for draft before critiquing, so it survives a failed critique.
    draft_id = db.create_draft(conn, idea_id, round_, draft["caption"], draft["slides"], None)
    flags = _invoke(
        conn, idea_id, daily_cap_usd, "critique_draft",
        lambda: ai_module.critique_draft(client, draft, brand_pack),
        on_step=on_step,
    )
    db.update_draft_quality_flags(conn, draft_id, flags)

    while flags and round_ < ai_module.MAX_REVISION_ROUNDS:
        round_ += 1
        draft = _invoke(
            conn, idea_id, daily_cap_usd, "revise_draft",
            lambda: ai_module.revise_draft(client, draft, flags, brand_pack),
            on_step=on_step,
        )
        draft_id = db.create_draft(conn, idea_id, round_, draft["caption"], draft["slides"], None)
        flags = _invoke(
            conn, idea_id, daily_cap_usd, "critique_draft",
            lambda: ai_module.critique_draft(client, draft, brand_pack),
            on_step=on_step,
        )
        db.update_draft_quality_flags(conn, draft_id, flags)

    db.update_idea_status(conn, idea_id, "reviewed")
    return draft, flags, round_


def ensure_image_folder(conn, idea, images_root, storage_module=storage):
    """Compute (once) and persist the per-carousel folder name, or return the
    existing one — so regenerating a single slide always lands in the same
    place instead of picking a new folder each time."""
    if idea.get("image_folder") and storage_module.is_valid_folder_name(idea["image_folder"]):
        folder = idea["image_folder"]
    else:
        date_str = datetime.now(timezone.utc).date().isoformat()
        folder = storage_module.make_carousel_folder(images_root, idea["topic"], date_str)
        db.set_idea_image_folder(conn, idea["id"], folder)
        idea["image_folder"] = folder
    Path(images_root, folder).mkdir(parents=True, exist_ok=True)
    return folder


def generate_slide_image(
    gemini_client, conn, idea, slide_index, slide_role, slide_text, prompt,
    images_root, daily_cap_usd, image_gen_module=image_gen, render_module=render,
    storage_module=storage, on_step=None,
):
    idea_id = idea["id"]

    if on_step:
        on_step("generate_image", "running")
    if db.would_exceed_daily_cap(conn, ESTIMATED_MAX_CALL_COST_USD, daily_cap_usd):
        error = DailyBudgetExceededError(
            f"This call could push today's spend over the ${daily_cap_usd:.2f} daily cap. "
            "Try again tomorrow or raise MAX_DAILY_SPEND_USD."
        )
        if on_step:
            on_step("generate_image", "error", str(error))
        raise error
    try:
        image_bytes, tokens_in, tokens_out, cost = image_gen_module.generate_image(gemini_client, prompt)
    except Exception as e:
        if on_step:
            on_step("generate_image", "error", str(e))
        raise
    db.log_api_call(conn, "generate_image", tokens_in, tokens_out, cost, idea_id=idea_id)
    if on_step:
        on_step("generate_image", "done")

    folder = ensure_image_folder(conn, idea, images_root, storage_module=storage_module)

    if on_step:
        on_step("render_image", "running")
    try:
        html = render_module.build_slide_html(slide_text, image_bytes, idea["brand_pack"], slide_role)
        png_bytes = render_module.render_png(html)
        file_path = Path(images_root) / folder / f"slide-{slide_index:02d}.png"
        file_path.write_bytes(png_bytes)
    except Exception as e:
        if on_step:
            on_step("render_image", "error", str(e))
        raise
    if on_step:
        on_step("render_image", "done")

    slide_image_id = db.create_slide_image(conn, idea_id, slide_index, prompt, str(file_path), cost)
    return db.get_slide_image(conn, slide_image_id)


def approve_slide_image(conn, slide_image_id):
    db.update_slide_image_status(conn, slide_image_id, "approved")


def reject_slide_image(conn, slide_image_id):
    db.update_slide_image_status(conn, slide_image_id, "rejected")


def maybe_mark_images_ready(conn, idea_id, total_slides):
    latest = db.get_latest_slide_images(conn, idea_id)
    if len(latest) == total_slides and all(row["status"] == "approved" for row in latest):
        db.update_idea_status(conn, idea_id, "images_ready")
