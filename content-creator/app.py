from pathlib import Path

import streamlit as st

import ai
import config
import db
import image_gen
import pipeline
import storage
import theme

st.set_page_config(page_title="Content Creator", layout="wide")
theme.inject_theme()

cfg = config.load_config()
conn = db.get_connection(cfg.db_path)
db.init_db(conn)
client = ai.get_client(cfg.api_key)
gemini_client = image_gen.get_client(cfg.gemini_api_key)
images_root = storage.images_root(cfg.db_path)

TONES = ai.load_tone_names(cfg.brand_pack)

STEP_LABELS = {
    "extract_topics": "A analisar o texto de referência",
    "generate_draft": "A gerar o rascunho",
    "critique_draft": "A rever a qualidade",
    "revise_draft": "A corrigir problemas encontrados",
    "generate_image": "A gerar a imagem",
    "render_image": "A compor o slide",
}


def run_with_progress(fn, *args, **kwargs):
    """Runs fn (a pipeline.* call) showing a live step checklist via st.status.
    On failure, marks the failed step and opens an error box with the raw
    exception for troubleshooting, then re-raises so existing callers'
    except-blocks still handle the friendly error message as before."""
    lines = {}

    with st.status("A processar...", expanded=True) as status:
        placeholder = st.empty()

        def render():
            placeholder.markdown("\n\n".join(lines.values()))

        def on_step(step, step_status, detail=None):
            label = STEP_LABELS.get(step, step)
            if step_status == "running":
                lines[step] = f"⏳ {label}..."
            elif step_status == "done":
                lines[step] = f"✅ {label}"
            elif step_status == "error":
                lines[step] = f"❌ {label} — falhou"
            render()

        try:
            result = fn(*args, on_step=on_step, **kwargs)
        except image_gen.NoImageReturned as e:
            # An expected outcome (Gemini simply didn't return an image this
            # time), not a crash — keep the status gentle instead of "Falhou".
            status.update(label="Sem imagem desta vez", state="complete")
            with st.expander("Detalhes (para diagnóstico)", expanded=False):
                st.code(f"{type(e).__name__}: {e}")
            raise
        except Exception as e:
            status.update(label="Falhou", state="error")
            with st.expander("Detalhes do erro (para diagnóstico)", expanded=True):
                st.code(f"{type(e).__name__}: {e}")
            raise
        else:
            status.update(label="Concluído", state="complete")
            return result

def render_reviewed_draft(conn, idea):
    """Shows the latest draft of a "reviewed" idea with Aprovar/Rejeitar,
    loaded straight from the DB so it survives a reload."""
    draft = db.list_drafts_for_idea(conn, idea["id"])[-1]
    flags = draft["quality_flags"]
    st.subheader("Legenda")
    st.write(draft["caption"])
    st.subheader("Slides")
    for i, slide in enumerate(draft["slides"], start=1):
        st.write(f"**Slide {i}:** {slide}")
    if flags:
        remaining = ", ".join(f["criterion"] for f in flags)
        st.warning(f"Pontos ainda não resolvidos após {draft['round']} ronda(s): {remaining}")
    col1, col2 = st.columns(2)
    if col1.button("Aprovar", key=f"approve_draft_{idea['id']}"):
        db.update_idea_status(conn, idea["id"], "approved")
        st.toast("Rascunho aprovado.")
        st.rerun()
    if col2.button("Rejeitar", key=f"reject_draft_{idea['id']}"):
        db.update_idea_status(conn, idea["id"], "rejected")
        st.toast("Rascunho rejeitado.")
        st.rerun()


theme.render_header(f"Content Creator — {cfg.brand_pack}")

tab_new, tab_images, tab_library = st.tabs(["Nova Ideia", "Gerar Imagens", "Biblioteca"])

with tab_new:
    st.subheader("1. Fonte")
    input_mode = st.radio("Como queres começar?", ["Tópico directo", "Texto de referência"])

    if input_mode == "Tópico directo":
        topic_input = st.text_input("Tópico")
        if st.button("Criar ideia") and topic_input:
            idea_id = db.create_idea(conn, cfg.brand_pack, "manual", topic_input)
            st.success(f"Ideia criada (#{idea_id}).")
    else:
        reference_text = st.text_area("Cola aqui o texto de referência", height=300)
        if st.button("Extrair tópicos") and reference_text:
            try:
                ai.validate_reference_length(reference_text)
            except ai.ReferenceTooLongError as e:
                st.error(str(e))
            else:
                try:
                    topics = run_with_progress(
                        pipeline.run_extraction,
                        client, conn, reference_text, cfg.brand_pack, cfg.max_daily_spend_usd,
                    )
                except pipeline.DailyBudgetExceededError as e:
                    st.error(str(e))
                else:
                    st.session_state["candidate_topics"] = topics
                    st.session_state["reference_text"] = reference_text

        candidates = st.session_state.get("candidate_topics", [])
        if candidates:
            st.subheader("2. Escolhe os tópicos")
            selected = []
            for i, c in enumerate(candidates):
                if st.checkbox(f"{c['topic']} ({c['pillar']})", key=f"topic_{i}"):
                    selected.append(c)
            if st.button("Criar ideias seleccionadas") and selected:
                created_ids = [
                    db.create_idea(
                        conn, cfg.brand_pack, "reference", c["topic"],
                        reference_text=st.session_state["reference_text"], pillar=c["pillar"],
                    )
                    for c in selected
                ]
                st.success(f"{len(created_ids)} ideia(s) criada(s).")

    st.subheader("3. Gerar rascunho")
    pending = db.list_ideas(conn, brand_pack=cfg.brand_pack, status="idea")
    if pending:
        options = {f"#{i['id']} — {i['topic']}": i for i in pending}
        chosen_label = st.selectbox("Ideia a rascunhar", list(options.keys()))
        chosen_idea = options[chosen_label]
        suggested_tone = ai.suggest_default_tone(cfg.brand_pack, chosen_idea["pillar"])
        tone_index = TONES.index(suggested_tone) if suggested_tone in TONES else 0
        tone = st.selectbox("Tom", TONES, index=tone_index)
        if st.button("Gerar rascunho"):
            try:
                run_with_progress(
                    pipeline.run_generation_pipeline,
                    client, conn, chosen_idea, tone, cfg.brand_pack, cfg.max_daily_spend_usd,
                )
            except pipeline.DailyBudgetExceededError as e:
                st.error(str(e))
            else:
                st.session_state["reviewed_idea_select"] = (
                    f"#{chosen_idea['id']} — {chosen_idea['topic']}"
                )
                st.rerun()
    else:
        st.info("Sem ideias pendentes. Cria uma acima.")

    st.subheader("Rascunhos à espera da tua decisão")
    reviewed = db.list_ideas(conn, brand_pack=cfg.brand_pack, status="reviewed")
    if reviewed:
        reviewed_options = {f"#{i['id']} — {i['topic']}": i for i in reviewed}
        reviewed_label = st.selectbox(
            "Rascunho", list(reviewed_options.keys()), key="reviewed_idea_select",
        )
        render_reviewed_draft(conn, reviewed_options[reviewed_label])
    else:
        st.info("Sem rascunhos à espera de decisão.")

with tab_images:
    st.subheader("Gerar Imagens do Carrossel")
    approved = (
        db.list_ideas(conn, brand_pack=cfg.brand_pack, status="approved")
        + db.list_ideas(conn, brand_pack=cfg.brand_pack, status="images_ready")
    )
    if not approved:
        st.info("Sem ideias aprovadas. Aprova um rascunho na aba 'Nova Ideia' primeiro.")
    else:
        options = {f"#{i['id']} — {i['topic']}": i for i in approved}
        chosen_label = st.selectbox("Ideia", list(options.keys()), key="img_idea_select")
        idea = db.get_idea(conn, options[chosen_label]["id"])
        latest_draft = db.list_drafts_for_idea(conn, idea["id"])[-1]
        slides = latest_draft["slides"]
        existing_images = {img["slide_index"]: img for img in db.get_latest_slide_images(conn, idea["id"])}

        for i, slide_text in enumerate(slides):
            role = "hero" if i == 0 else "card"
            st.markdown(f"**Slide {i + 1}** ({'capa' if role == 'hero' else 'cartão'})")
            existing = existing_images.get(i)

            if existing:
                st.image(existing["file_path"], width=300)
                if existing["status"] == "approved":
                    st.success("Aprovado")
                col1, col2, col3 = st.columns(3)
                if existing["status"] != "approved" and col1.button("Aprovar", key=f"approve_{i}"):
                    pipeline.approve_slide_image(conn, existing["id"])
                    pipeline.maybe_mark_images_ready(conn, idea["id"], len(slides))
                    st.rerun()
                if col2.button("Gerar novamente", key=f"regen_{i}"):
                    st.session_state[f"show_prompt_{idea['id']}_{i}"] = True
                background = Path(existing["file_path"]).with_name(f"slide-{i:02d}-bg.png")
                if background.is_file() and col3.button(
                    "Refazer layout", key=f"rerender_{i}",
                    help="Volta a compor o slide com a mesma imagem, sem custo.",
                ):
                    run_with_progress(
                        lambda on_step: pipeline.rerender_slide_image(
                            conn, idea, i, role, slide_text, images_root, i == len(slides) - 1,
                            on_step=on_step,
                        ),
                    )
                    st.rerun()

            if not existing or st.session_state.get(f"show_prompt_{idea['id']}_{i}"):
                prompt_key = f"prompt_{idea['id']}_{i}"
                if prompt_key not in st.session_state:
                    st.session_state[prompt_key] = image_gen.build_image_prompt(slide_text, cfg.brand_pack, role)
                st.session_state[prompt_key] = st.text_area(
                    "Prompt da imagem (podes editar)", value=st.session_state[prompt_key],
                    key=f"prompt_area_{idea['id']}_{i}",
                )
                if st.button("Gerar imagem", key=f"generate_{i}"):
                    try:
                        run_with_progress(
                            lambda on_step: pipeline.generate_slide_image(
                                gemini_client, conn, idea, i, role, slide_text,
                                st.session_state[prompt_key], images_root, cfg.max_daily_spend_usd,
                                on_step=on_step, is_last=i == len(slides) - 1,
                            ),
                        )
                    except pipeline.DailyBudgetExceededError as e:
                        st.error(str(e))
                    except image_gen.NoImageReturned:
                        st.warning(
                            "Desta vez não veio imagem. Tenta gerar outra vez, "
                            "ou ajusta um pouco o prompt."
                        )
                    else:
                        st.session_state[f"show_prompt_{idea['id']}_{i}"] = False
                        st.rerun()

        st.divider()
        st.subheader("Pré-visualização do Carrossel")
        latest = db.get_latest_slide_images(conn, idea["id"])
        approved_images = [img for img in latest if img["status"] == "approved"]
        if len(approved_images) == len(slides):
            preview_key = f"carousel_preview_index_{idea['id']}"
            if preview_key not in st.session_state:
                st.session_state[preview_key] = 0
            idx = st.session_state[preview_key]
            st.image(approved_images[idx]["file_path"], width=400)
            st.caption(slides[idx])
            col_prev, col_next = st.columns(2)
            if col_prev.button("◀ Anterior") and idx > 0:
                st.session_state[preview_key] -= 1
                st.rerun()
            if col_next.button("Seguinte ▶") and idx < len(slides) - 1:
                st.session_state[preview_key] += 1
                st.rerun()
            thumb_cols = st.columns(len(slides))
            for j, col in enumerate(thumb_cols):
                if col.button(f"{j + 1}", key=f"thumb_{j}"):
                    st.session_state[preview_key] = j
                    st.rerun()
            st.write(f"**Legenda:** {latest_draft['caption']}")
        else:
            st.info("Aprova todas as imagens para veres a pré-visualização do carrossel.")

with tab_library:
    st.subheader("Biblioteca")
    show_archived = st.checkbox("Mostrar arquivadas")
    ideas = db.list_ideas(conn, brand_pack=cfg.brand_pack, include_archived=show_archived)
    spend_today = db.get_spend_today(conn)
    st.caption(f"Gasto hoje: ${spend_today:.2f} / ${cfg.max_daily_spend_usd:.2f}")
    for idea in ideas:
        with st.expander(f"#{idea['id']} — {idea['topic']} ({idea['status']})"):
            for d in db.list_drafts_for_idea(conn, idea["id"]):
                st.write(f"Ronda {d['round']}: {d['caption'][:120]}...")
            if idea["archived_at"] is None:
                if st.button("Arquivar", key=f"archive_{idea['id']}"):
                    db.archive_idea(conn, idea["id"])
                    st.toast("Ideia arquivada.")
                    st.rerun()
            else:
                if st.button("Eliminar definitivamente", key=f"delete_{idea['id']}"):
                    db.hard_delete_idea(conn, idea["id"])
                    st.toast("Ideia eliminada.")
                    st.rerun()
