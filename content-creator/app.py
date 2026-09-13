import streamlit as st

import ai
import config
import db
import pipeline

st.set_page_config(page_title="Content Creator", layout="wide")

cfg = config.load_config()
conn = db.get_connection(cfg.db_path)
db.init_db(conn)
client = ai.get_client(cfg.api_key)

TONES = ai.load_tone_names(cfg.brand_pack)

st.title(f"Content Creator — {cfg.brand_pack}")

tab_new, tab_library = st.tabs(["Nova Ideia", "Biblioteca"])

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
                    topics = pipeline.run_extraction(
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
                draft, flags, rounds = pipeline.run_generation_pipeline(
                    client, conn, chosen_idea, tone, cfg.brand_pack, cfg.max_daily_spend_usd,
                )
            except pipeline.DailyBudgetExceededError as e:
                st.error(str(e))
            else:
                st.session_state["current_result"] = {
                    "draft": draft,
                    "flags": flags,
                    "rounds": rounds,
                    "idea": chosen_idea,
                }
    else:
        st.info("Sem ideias pendentes. Cria uma acima.")

    # Rendered outside the "Gerar rascunho" button block so the Aprovar/Rejeitar
    # buttons survive the rerun a nested button click would otherwise discard.
    if "current_result" in st.session_state:
        result = st.session_state["current_result"]
        draft, flags, rounds, idea = (
            result["draft"], result["flags"], result["rounds"], result["idea"],
        )
        st.subheader("Legenda")
        st.write(draft["caption"])
        st.subheader("Slides")
        for i, slide in enumerate(draft["slides"], start=1):
            st.write(f"**Slide {i}:** {slide}")
        if flags:
            remaining = ", ".join(f["criterion"] for f in flags)
            st.warning(f"Pontos ainda não resolvidos após {rounds} ronda(s): {remaining}")
        col1, col2 = st.columns(2)
        if col1.button("Aprovar"):
            db.update_idea_status(conn, idea["id"], "approved")
            del st.session_state["current_result"]
        if col2.button("Rejeitar"):
            db.update_idea_status(conn, idea["id"], "rejected")
            del st.session_state["current_result"]

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
            else:
                if st.button("Eliminar definitivamente", key=f"delete_{idea['id']}"):
                    db.hard_delete_idea(conn, idea["id"])
