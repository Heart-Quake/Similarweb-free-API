from __future__ import annotations

import streamlit as st

from ui_builders import (
    format_decimal_display,
    format_int_display,
    format_rank_display,
    get_ai_traffic_summary,
    get_global_rank,
    get_large_screenshot_url,
    get_latest_data_period,
    get_latest_monthly_visits,
    get_site_name,
    get_snapshot_label,
    get_unique_visitors,
)


def inject_app_styles() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&display=swap');

            :root {
                --sw-blue: #2563eb;
                --sw-ink: #0f172a;
                --sw-teal: #0f766e;
                --sw-gold: #f59e0b;
                --sw-surface: #f8fafc;
                --sw-border: rgba(15, 23, 42, 0.08);
            }

            html, body, [class*="css"] {
                font-family: 'Space Grotesk', sans-serif;
            }

            .sw-hero {
                background: linear-gradient(135deg, rgba(37, 99, 235, 0.10), rgba(15, 118, 110, 0.08));
                border: 1px solid var(--sw-border);
                border-radius: 24px;
                padding: 1.4rem 1.5rem;
                margin-bottom: 1rem;
            }

            .sw-hero h1 {
                margin: 0;
                color: var(--sw-ink);
                font-size: 2rem;
                line-height: 1.1;
            }

            .sw-hero p {
                margin: 0.45rem 0 0;
                color: rgba(15, 23, 42, 0.72);
                font-size: 0.98rem;
            }

            .sw-banner {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 0.75rem;
                margin: 0.8rem 0 1.2rem;
            }

            .sw-banner-card {
                background: white;
                border: 1px solid var(--sw-border);
                border-radius: 18px;
                padding: 0.9rem 1rem;
            }

            .sw-banner-card small {
                display: block;
                color: rgba(15, 23, 42, 0.56);
                margin-bottom: 0.35rem;
            }

            .sw-banner-card strong {
                color: var(--sw-ink);
                font-size: 1.05rem;
            }

            .sw-note {
                color: rgba(15, 23, 42, 0.68);
                font-size: 0.92rem;
                margin-top: 0.35rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_hero() -> None:
    st.markdown(
        """
        <section class="tool-hero">
            <div class="tool-kicker">Traffic intelligence</div>
            <h1 class="tool-title">Similarweb Free API Cockpit</h1>
            <p class="tool-lead">Compare rapidement des domaines avec les donnees de trafic Similarweb disponibles.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_content() -> None:
    with st.sidebar:
        st.header("Informations")
        st.markdown(
            """
            - Trafic estime et classements
            - Mix des sources de trafic
            - Top pays et top mots-cles
            - Signaux IA quand l'API les expose
            - Historique local des collectes
            """
        )
        st.caption("Les dates affichees distinguent la date de collecte locale et la periode de donnee du snapshot Similarweb.")


def render_context_banner(summary: dict, title: str = "Contexte d'analyse") -> None:
    st.markdown(f"### {title}")
    cards = [
        ("Domaines", summary.get("total", 0)),
        ("Succes", summary.get("success", 0)),
        ("Erreurs", summary.get("error", 0)),
        ("Cache", "ON" if summary.get("use_cache") else "OFF"),
        ("Snapshot API", summary.get("latest_snapshot", "N/A")),
        ("Periode donnee", summary.get("latest_period", "N/A")),
    ]
    if summary.get("rate_limited_count"):
        cards.append(("Blocages", summary.get("rate_limited_count", 0)))
    if summary.get("elapsed_time") is not None:
        cards.append(("Temps", f"{summary['elapsed_time']:.2f}s"))

    html = ["<div class='sw-banner'>"]
    for label, value in cards:
        html.append(
            f"<div class='sw-banner-card'><small>{label}</small><strong>{value}</strong></div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)
    st.markdown(
        "<div class='sw-note'>Date de collecte locale = moment ou votre outil a appele l'API. Periode de donnee = mois du snapshot Similarweb visible dans le payload.</div>",
        unsafe_allow_html=True,
    )
    if summary.get("warning_message"):
        if summary.get("warning_level") == "error":
            st.error(summary["warning_message"])
        else:
            st.warning(summary["warning_message"])


def render_single_overview(site_data: dict, fallback_domain: str) -> None:
    site_name = get_site_name(site_data, fallback_domain)
    latest_visits = get_latest_monthly_visits(site_data)
    unique_visitors = get_unique_visitors(site_data)
    rank = get_global_rank(site_data)
    engagements = site_data.get("Engagments") if isinstance(site_data.get("Engagments"), dict) else {}
    bounce_rate = float(engagements.get("BounceRate", 0)) * 100 if engagements.get("BounceRate") is not None else None
    pages_per_visit = float(engagements.get("PagePerVisit", 0)) if engagements.get("PagePerVisit") is not None else None

    st.markdown(f"## {site_name}")
    render_context_banner(
        {
            "total": 1,
            "success": 1,
            "error": 0,
            "use_cache": True,
            "latest_snapshot": get_snapshot_label(site_data),
            "latest_period": get_latest_data_period(site_data),
        },
        title="Lecture du snapshot",
    )

    cols = st.columns(5)
    cols[0].metric("Visites mensuelles", format_int_display(latest_visits))
    cols[1].metric("Classement global", format_rank_display(rank))
    cols[2].metric("Bounce rate", f"{bounce_rate:.2f}%" if bounce_rate is not None else "N/A")
    cols[3].metric("Pages / visite", format_decimal_display(pages_per_visit))
    cols[4].metric("Visites uniques", format_int_display(unique_visitors) if unique_visitors is not None else "N/A")


def render_screenshot(site_data: dict, caption: str = "Capture du site") -> None:
    screenshot_url = get_large_screenshot_url(site_data)
    if screenshot_url:
        st.image(screenshot_url, caption=caption, use_column_width=True)
    else:
        st.info("Aucune capture disponible dans le payload.")


def render_ai_summary(site_data: dict) -> None:
    ai_summary = get_ai_traffic_summary(site_data)
    if not ai_summary["top_chatbots"] and not ai_summary["prompts"]:
        st.info("Aucun detail IA disponible pour ce domaine.")
        return

    cols = st.columns(2)
    cols[0].metric(
        "Visites issues de l'IA",
        format_decimal_display(ai_summary["total_visits"], 0) if ai_summary["total_visits"] is not None else "N/A",
    )
    cols[1].metric(
        "Part du trafic referent IA",
        f"{ai_summary['referral_share_pct']:.3f}%" if ai_summary["referral_share_pct"] is not None else "N/A",
    )

    if ai_summary["prompts"]:
        st.markdown("**Top prompts exposes par l'API**")
        for prompt in ai_summary["prompts"][:5]:
            st.markdown(f"- {prompt}")
