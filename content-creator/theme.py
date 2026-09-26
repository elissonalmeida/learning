import html

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
/* Slides open big through our own "Ver maior" (#47): hide the built-in
   fullscreen button on images only, so there is one obvious path. */
[data-testid="stElementContainer"]:has([data-testid="stImage"]) [data-testid="stElementToolbar"] {
    display: none;
}
</style>
"""


def inject_theme():
    st.markdown(HEADER_CSS, unsafe_allow_html=True)


def render_header(title):
    st.markdown(
        f'<div class="app-header"><span class="app-header-title">{html.escape(title)}</span></div>',
        unsafe_allow_html=True,
    )
