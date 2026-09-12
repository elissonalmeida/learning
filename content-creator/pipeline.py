import ai
import db

ESTIMATED_MAX_CALL_COST_USD = 0.20


class DailyBudgetExceededError(Exception):
    pass


def _invoke(conn, idea_id, daily_cap_usd, function_name, ai_call):
    if db.would_exceed_daily_cap(conn, ESTIMATED_MAX_CALL_COST_USD, daily_cap_usd):
        raise DailyBudgetExceededError(
            f"This call could push today's spend over the ${daily_cap_usd:.2f} daily cap. "
            "Try again tomorrow or raise MAX_DAILY_SPEND_USD."
        )
    result, tokens_in, tokens_out, cost = ai_call()
    db.log_api_call(conn, function_name, tokens_in, tokens_out, cost, idea_id=idea_id)
    return result


def run_generation_pipeline(client, conn, idea, tone, brand_pack, daily_cap_usd, ai_module=ai):
    idea_id = idea["id"]

    draft = _invoke(
        conn, idea_id, daily_cap_usd, "generate_draft",
        lambda: ai_module.generate_draft(client, idea["topic"], tone, idea["pillar"], brand_pack),
    )
    round_ = 0
    flags = _invoke(
        conn, idea_id, daily_cap_usd, "critique_draft",
        lambda: ai_module.critique_draft(client, draft, brand_pack),
    )
    db.create_draft(conn, idea_id, round_, draft["caption"], draft["slides"], flags)

    while flags and round_ < ai.MAX_REVISION_ROUNDS:
        round_ += 1
        draft = _invoke(
            conn, idea_id, daily_cap_usd, "revise_draft",
            lambda: ai_module.revise_draft(client, draft, flags, brand_pack),
        )
        flags = _invoke(
            conn, idea_id, daily_cap_usd, "critique_draft",
            lambda: ai_module.critique_draft(client, draft, brand_pack),
        )
        db.create_draft(conn, idea_id, round_, draft["caption"], draft["slides"], flags)

    db.update_idea_status(conn, idea_id, "reviewed")
    return draft, flags, round_
