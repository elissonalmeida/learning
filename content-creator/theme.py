import streamlit as st

HEADER_CSS = """
<style>
.app-header {
    background: #3E2208;
    padding: 12px 18px;
    border-radius: 0.75rem;
    margin-bottom: 1rem;
}
.app-header-title {
    font-family: "Cormorant Garamond", serif;
    font-size: 28px;
    color: #C4922A;
    letter-spacing: 1px;
    margin: 0;
}
</style>
"""


def inject_theme():
    st.markdown(HEADER_CSS, unsafe_allow_html=True)


def render_header(title):
    st.markdown(
        f'<div class="app-header"><span class="app-header-title">{title}</span></div>',
        unsafe_allow_html=True,
    )
