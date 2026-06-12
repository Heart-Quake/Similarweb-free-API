from __future__ import annotations

from pathlib import Path

import streamlit as st

LOGO_PATH = Path(__file__).with_name("logo-full-cream.png")


def apply_automation_seo_theme() -> None:
    if LOGO_PATH.exists():
        st.sidebar.image(str(LOGO_PATH), width=180)

    st.markdown(
        """
        <style>
            :root {
                --yn-bg: #222429;
                --yn-deep: #0F1011;
                --yn-card: #27282A;
                --yn-card-strong: #1F2024;
                --yn-card-hover: #1B1C1E;
                --yn-border: #37383A;
                --yn-text: #F7F8F8;
                --yn-muted: #A1A1AA;
                --yn-muted-strong: #828282;
                --yn-accent: #49DCBC;
                --yn-success: #4CEBA6;
                --yn-danger: #FF3366;
                --yn-ring: rgba(73, 220, 188, 0.42);
                --yn-shadow: 0 18px 44px rgba(0, 0, 0, 0.24);
            }

            .stApp {
                background: var(--yn-bg);
                color: var(--yn-text);
            }

            [data-testid="stAppViewContainer"],
            [data-testid="stHeader"] {
                background: transparent;
            }

            .block-container {
                max-width: 1180px;
                padding-top: 1.6rem;
                padding-bottom: 4rem;
            }

            h1, h2, h3, h4 {
                color: var(--yn-text) !important;
                letter-spacing: 0;
            }

            p, label, span, div {
                letter-spacing: 0;
            }

            [data-testid="stSidebar"] {
                background: var(--yn-deep);
                border-right: 1px solid var(--yn-border);
            }

            [data-testid="stSidebar"] h1,
            [data-testid="stSidebar"] h2,
            [data-testid="stSidebar"] h3 {
                color: var(--yn-text) !important;
            }

            [data-testid="stSidebar"] label,
            [data-testid="stSidebar"] p,
            [data-testid="stSidebar"] span {
                color: var(--yn-muted) !important;
            }

            [data-testid="stSidebar"] input,
            [data-testid="stSidebar"] textarea,
            [data-testid="stSidebar"] [role="combobox"],
            [data-testid="stSidebar"] [data-baseweb="select"] > div,
            [data-testid="stSidebar"] [data-baseweb="input"] > div,
            [data-testid="stSidebar"] [data-baseweb="textarea"] > div {
                background: var(--yn-card-strong) !important;
                border: 1px solid var(--yn-border) !important;
                border-radius: 8px !important;
                color: var(--yn-text) !important;
            }

            [data-testid="stSidebar"] input,
            [data-testid="stSidebar"] textarea,
            [data-testid="stSidebar"] [data-baseweb="select"] span,
            [data-testid="stSidebar"] [data-baseweb="select"] div,
            [data-testid="stSidebar"] [role="combobox"] {
                color: var(--yn-text) !important;
                -webkit-text-fill-color: var(--yn-text) !important;
            }

            input::placeholder,
            textarea::placeholder {
                color: var(--yn-muted-strong) !important;
                opacity: 1 !important;
                -webkit-text-fill-color: var(--yn-muted-strong) !important;
            }

            [data-baseweb="select"] svg {
                fill: var(--yn-muted) !important;
            }

            [data-baseweb="select"]:focus-within > div,
            [data-baseweb="input"]:focus-within > div,
            [data-baseweb="textarea"]:focus-within > div {
                border-color: var(--yn-accent) !important;
                box-shadow: 0 0 0 2px var(--yn-ring) !important;
            }

            [data-baseweb="popover"] [role="listbox"],
            [data-baseweb="menu"] {
                background: var(--yn-card-strong) !important;
                border: 1px solid var(--yn-border) !important;
                color: var(--yn-text) !important;
            }

            [data-baseweb="popover"] [role="option"],
            [data-baseweb="menu"] li {
                background: var(--yn-card-strong) !important;
                color: var(--yn-text) !important;
            }

            [data-baseweb="popover"] [role="option"]:hover,
            [data-baseweb="menu"] li:hover {
                background: var(--yn-card-hover) !important;
            }

            [data-baseweb="popover"] [role="option"][aria-selected="true"],
            [data-baseweb="popover"] [role="option"][aria-checked="true"],
            [role="option"][aria-selected="true"],
            [role="option"][aria-checked="true"] {
                background: rgba(73, 220, 188, 0.16) !important;
                color: var(--yn-text) !important;
            }

            .stButton > button,
            .stDownloadButton > button,
            [data-testid="stFormSubmitButton"] button {
                background: var(--yn-text) !important;
                border: 1px solid var(--yn-text) !important;
                border-radius: 8px !important;
                color: var(--yn-deep) !important;
                font-weight: 800 !important;
                min-height: 2.45rem;
                transition: background-color 160ms ease, border-color 160ms ease, transform 160ms ease;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover,
            [data-testid="stFormSubmitButton"] button:hover {
                background: var(--yn-accent) !important;
                border-color: var(--yn-accent) !important;
                color: var(--yn-deep) !important;
                transform: translateY(-1px);
            }

            [data-testid="stTabs"] [role="tablist"] {
                gap: 0.35rem;
                border-bottom: 1px solid var(--yn-border);
            }

            [data-testid="stTabs"] [role="tab"] {
                color: var(--yn-muted) !important;
                border-radius: 8px 8px 0 0;
            }

            [data-testid="stTabs"] [aria-selected="true"] {
                color: var(--yn-accent) !important;
            }

            [data-testid="stMetric"],
            [data-testid="stExpander"],
            [data-testid="stDataFrame"],
            div[data-testid="stAlert"] {
                background: var(--yn-card) !important;
                border: 1px solid var(--yn-border) !important;
                border-radius: 8px !important;
                box-shadow: var(--yn-shadow);
            }

            hr {
                border-color: var(--yn-border);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
