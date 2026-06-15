from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from automation_seo_theme import apply_automation_seo_theme
import similar
from cache import SQLiteCache
from config import APP_VERSION, DEFAULT_RETRY_COUNT, NETWORK_PRESETS
from core_async import AsyncSimilarClient
from rate_state import get_controller
from ui_builders import (
    build_batch_context_summary,
    build_domain_row,
    build_history_dataframe,
    build_period_analysis_row,
    clean_category_name,
    get_error_diagnostic,
    get_error_label,
    get_user_facing_error_message,
    get_ai_traffic_summary,
    get_category_rank_label,
    get_country_rank_label,
    get_latest_data_period,
    get_site_name,
    get_snapshot_label,
    get_top_keyword_rows,
    is_valid_result,
    should_save_to_history,
    split_batch_results,
)
from ui_charts import (
    PRIMARY_BLUE,
    SUCCESS_GREEN,
    WARNING_ORANGE,
    create_ai_chatbots_figure,
    create_ai_trend_figure,
    create_engagement_figure,
    create_history_metric_figure,
    create_top_countries_figure,
    create_top_keywords_figure,
    create_traffic_sources_figure,
    create_visits_trend_figure,
)
from ui_exports import render_export_panel
from ui_summary import (
    inject_app_styles,
    render_ai_summary,
    render_app_hero,
    render_context_banner,
    render_screenshot,
    render_sidebar_content,
    render_single_overview,
)
from ui_tables import render_batch_dataframe, render_error_dataframe, render_history_dataframe, render_keywords_table


st.set_page_config(page_title="Similarweb Free API Cockpit", page_icon="📊", layout="wide")
inject_app_styles()
apply_automation_seo_theme()
render_sidebar_content()
render_app_hero()


def format_epoch_label(timestamp: float) -> str:
    if not timestamp:
        return "N/A"
    return datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y %H:%M:%S")


def get_process_started_label() -> str:
    try:
        output = subprocess.check_output(
            ["ps", "-p", str(os.getpid()), "-o", "lstart="],
            text=True,
            timeout=2,
        ).strip()
        return output or "N/A"
    except (OSError, subprocess.SubprocessError):
        return "N/A"


def render_runtime_status() -> None:
    snapshot = get_controller().get_snapshot()
    now = time.time()
    state_labels = {
        "CLOSED": "Pret",
        "HALF_OPEN": "Reprise prudente",
        "OPEN": "Cooldown actif",
    }

    st.caption(
        f"Version chargee / demarrage serveur: {APP_VERSION} | "
        f"PID {os.getpid()} | {get_process_started_label()}"
    )
    st.caption(f"Etat circuit breaker: {state_labels.get(snapshot.state, snapshot.state)}")
    if snapshot.last_block_at:
        st.caption(f"Dernier blocage: {format_epoch_label(snapshot.last_block_at)}")

    if snapshot.hard_cooldown_until > now:
        remaining_minutes = max(1, int((snapshot.hard_cooldown_until - now) / 60))
        st.warning(
            f"Cooldown Similarweb actif. Prochain essai recommande apres "
            f"{format_epoch_label(snapshot.hard_cooldown_until)} (~{remaining_minutes} min)."
        )
    else:
        st.success("Aucun cooldown actif.")


db_cache = SQLiteCache()

with st.sidebar:
    st.markdown("---")
    st.header("Runtime")
    render_runtime_status()
    st.markdown("---")
    st.header("Configuration reseau")
    use_proxies = st.checkbox("Utiliser des proxys", value=False)
    proxy_list = []
    if use_proxies:
        proxy_input = st.text_area(
            "Liste des proxys",
            height=120,
            help="Un proxy par ligne. Format: http://user:pass@host:port",
        )
        proxy_list = [value.strip() for value in proxy_input.splitlines() if value.strip()]
        if proxy_list:
            st.success(f"{len(proxy_list)} proxy(s) charge(s)")


VALID_RESULT_SESSION_KEYS = [
    "batch_results",
    "batch_use_cache",
    "batch_elapsed_time",
    "batch_success_rows",
    "batch_error_rows",
]
PROGRESS_UPDATE_INTERVAL_SECONDS = 0.25
PROGRESS_UPDATE_STEP = 5


def save_results_to_history(results: dict[str, dict]) -> None:
    entries = [
        (domain, payload, get_latest_data_period(payload))
        for domain, payload in results.items()
        if should_save_to_history(payload)
    ]
    if entries:
        similar.save_many_to_history(entries)


def parse_uploaded_domains(uploaded_file, max_domains: int) -> list[str]:
    uploaded_file.seek(0)
    if uploaded_file.name.endswith(".csv"):
        dataframe = pd.read_csv(uploaded_file)
        domain_column = None
        for column in dataframe.columns:
            lowered = column.lower()
            if any(keyword in lowered for keyword in ["domain", "url", "site", "website", "domaine"]):
                domain_column = column
                break
        selected_column = domain_column or dataframe.columns[0]
        return [value for value in dataframe[selected_column].dropna().astype(str).tolist()[:max_domains] if value.strip()]

    content = uploaded_file.read().decode("utf-8")
    return [line.strip() for line in content.splitlines() if line.strip()][:max_domains]


def estimate_runtime_label(domain_count: int, delay_value: float) -> str:
    estimated_minutes = (domain_count * float(delay_value)) / 60
    if estimated_minutes >= 60:
        return f"~{estimated_minutes / 60:.1f} heure(s)"
    return f"~{estimated_minutes:.1f} minute(s)"


def resolve_network_settings(preset_name: str, manual_delay: float, manual_max_concurrency: int) -> tuple[float, int]:
    preset = NETWORK_PRESETS.get(preset_name, NETWORK_PRESETS["Collecte longue sécurisée"])
    if preset_name == "Personnalise":
        return float(manual_delay), int(manual_max_concurrency)
    return float(preset["delay"]), int(preset["max_concurrency"])


def run_single_lookup(domain_input: str) -> dict | None:
    result = similar.similarGet(domain_input)
    if is_valid_result(result):
        similar.save_to_history(domain_input, result, period_label=get_latest_data_period(result))
    return result


def build_delay_range(delay_value: float) -> tuple[float, float]:
    # Garde un leger jitter pour lisser les pointes sans casser l'intention du delai cible.
    target_delay = max(0.15, float(delay_value or 0.5))
    lower_bound = max(0.15, target_delay - 0.35)
    upper_bound = max(lower_bound, target_delay + 0.35)
    return lower_bound, upper_bound


def run_batch_lookup(
    domains: list[str],
    delay_value: float,
    use_cache: bool,
    retry_count: int,
    chunk_size: int,
    proxy_list: list[str],
    max_concurrency: int,
) -> tuple[dict, float]:
    progress_bar = st.progress(0)
    status_text = st.empty()
    progress_state = {
        "last_update_at": 0.0,
        "last_step": 0,
    }

    def update_progress(current, total, domain, result):
        now = time.time()
        should_refresh = (
            current in {1, total}
            or current - progress_state["last_step"] >= PROGRESS_UPDATE_STEP
            or (now - progress_state["last_update_at"]) >= PROGRESS_UPDATE_INTERVAL_SECONDS
        )
        if not should_refresh:
            return

        progress_state["last_update_at"] = now
        progress_state["last_step"] = current
        progress_bar.progress(current / total if total else 0)
        if isinstance(result, dict) and result.get("error"):
            status_text.warning(f"[{current}/{total}] {domain} - {get_error_label(result)}")
        else:
            status_text.info(f"[{current}/{total}] {domain}")

    async def run_async_batch() -> dict:
        client = AsyncSimilarClient(
            cache=db_cache if use_cache else None,
            proxy_list=proxy_list,
            max_concurrency=max_concurrency,
            delay_range=build_delay_range(delay_value),
        )
        return await client.fetch_batch(
            domains,
            progress_callback=update_progress,
            chunk_size=chunk_size,
            use_cache=use_cache,
            retry_count=retry_count,
        )

    started_at = time.time()
    results = asyncio.run(run_async_batch())
    elapsed_time = time.time() - started_at
    progress_bar.progress(1.0)
    status_text.success(f"Termine en {elapsed_time:.2f}s")
    save_results_to_history(results)
    return results, elapsed_time


def render_batch_portfolio_charts(dataframe: pd.DataFrame) -> None:
    if dataframe.empty:
        return

    st.subheader("Vue portefeuille")
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    with col1:
        if {"Domaine", "Visites (M)"}.issubset(dataframe.columns):
            figure = px.bar(
                dataframe.sort_values("Visites (M)", ascending=False).head(15),
                x="Domaine",
                y="Visites (M)",
                color="Visites (M)",
                color_continuous_scale="Blues",
                title="Top domaines par visites",
            )
            figure.update_layout(height=360, showlegend=False, xaxis_title="", yaxis_title="Visites (M)")
            st.plotly_chart(figure, use_container_width=True)
        else:
            st.info("Pas assez de donnees pour comparer les volumes.")

    with col2:
        source_columns = [
            column
            for column in [
                "Trafic direct (%)",
                "Trafic organique (%)",
                "Trafic payant (%)",
                "Trafic reseaux sociaux (%)",
                "Trafic email (%)",
            ]
            if column in dataframe.columns
        ]
        if source_columns:
            source_means = dataframe[source_columns].mean(numeric_only=True).reset_index()
            source_means.columns = ["Source", "Pourcentage moyen"]
            figure = px.bar(
                source_means,
                x="Source",
                y="Pourcentage moyen",
                title="Mix trafic moyen du portefeuille",
                color_discrete_sequence=[SUCCESS_GREEN],
            )
            figure.update_layout(height=360, showlegend=False, xaxis_title="", yaxis_title="% moyen")
            st.plotly_chart(figure, use_container_width=True)
        else:
            st.info("Mix trafic indisponible.")

    with col3:
        country_rows = []
        for _, row in dataframe.iterrows():
            value = row.get("Top 3 Pays")
            if not value or value == "N/A":
                continue
            for chunk in str(value).split(","):
                code = chunk.split(":")[0].strip()
                if code:
                    country_rows.append({"Pays": code, "Occurrences": 1})
        country_df = pd.DataFrame(country_rows)
        if not country_df.empty:
            geo = country_df.groupby("Pays", as_index=False)["Occurrences"].sum().sort_values("Occurrences", ascending=False).head(10)
            figure = px.bar(
                geo,
                x="Occurrences",
                y="Pays",
                orientation="h",
                title="Pays les plus presents",
                color_discrete_sequence=[PRIMARY_BLUE],
            )
            figure.update_layout(height=360, showlegend=False, xaxis_title="Occurrences", yaxis_title="")
            st.plotly_chart(figure, use_container_width=True)
        else:
            st.info("Pas assez de signaux geographiques.")

    with col4:
        engagement_columns = [column for column in ["Taux de rebond (%)", "Pages par visite", "Duree (min)"] if column in dataframe.columns]
        if engagement_columns:
            engagement_df = dataframe[engagement_columns].mean(numeric_only=True).reset_index()
            engagement_df.columns = ["Metrique", "Valeur moyenne"]
            figure = px.bar(
                engagement_df,
                x="Metrique",
                y="Valeur moyenne",
                title="Engagement moyen du portefeuille",
                color_discrete_sequence=[WARNING_ORANGE],
            )
            figure.update_layout(height=360, showlegend=False, xaxis_title="", yaxis_title="Valeur")
            st.plotly_chart(figure, use_container_width=True)
        else:
            st.info("Pas assez de metriques d'engagement.")


def render_domain_explorer(valid_results: dict[str, dict], key_prefix: str, selected_domain: str | None = None) -> None:
    if not valid_results:
        st.info("Aucune donnee valide disponible pour l'exploration.")
        return

    domain_options = sorted(valid_results.keys())
    if selected_domain not in domain_options:
        selected_domain = domain_options[0]

    if len(domain_options) > 1:
        selected_domain = st.selectbox(
            "Selectionnez un domaine",
            domain_options,
            index=domain_options.index(selected_domain),
            key=f"domain_selector_{key_prefix}",
        )

    site_data = valid_results[selected_domain]
    site_name = get_site_name(site_data, selected_domain)

    render_single_overview(site_data, selected_domain)

    meta_cols = st.columns(4)
    meta_cols[0].metric("Classement pays", get_country_rank_label(site_data))
    meta_cols[1].metric("Classement categorie", get_category_rank_label(site_data))
    meta_cols[2].metric("Categorie", clean_category_name(site_data.get("Category")))
    meta_cols[3].metric("Snapshot API", get_snapshot_label(site_data))

    visual_col, screenshot_col = st.columns([1.35, 0.65])
    with screenshot_col:
        render_screenshot(site_data, caption=f"Capture de {site_name}")
    with visual_col:
        tabs = st.tabs(["Trend", "Mix trafic", "Geographie", "Engagement", "Mots-cles", "Trafic IA", "JSON"])

        with tabs[0]:
            figure = create_visits_trend_figure(site_data)
            if figure:
                st.plotly_chart(figure, use_container_width=True)
            else:
                st.info("Serie de visites indisponible.")

        with tabs[1]:
            figure = create_traffic_sources_figure(site_data)
            if figure:
                st.plotly_chart(figure, use_container_width=True)
            else:
                st.info("Mix trafic indisponible.")

        with tabs[2]:
            figure = create_top_countries_figure(site_data)
            if figure:
                st.plotly_chart(figure, use_container_width=True)
            else:
                st.info("Geographie indisponible.")

        with tabs[3]:
            figure = create_engagement_figure(site_data)
            if figure:
                st.plotly_chart(figure, use_container_width=True)
            else:
                st.info("Engagement indisponible.")

        with tabs[4]:
            keyword_figure = create_top_keywords_figure(site_data)
            if keyword_figure:
                st.plotly_chart(keyword_figure, use_container_width=True)
            keyword_rows = get_top_keyword_rows(site_data)
            keyword_df = render_keywords_table(keyword_rows, key=f"keywords_{key_prefix}")
            if not keyword_df.empty:
                st.download_button(
                    label="Telecharger les mots-cles CSV",
                    data=keyword_df.to_csv(index=False, encoding="utf-8-sig"),
                    file_name=f"similarweb_keywords_{selected_domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key=f"keywords_export_{key_prefix}",
                )

        with tabs[5]:
            render_ai_summary(site_data)
            ai_cols = st.columns(2)
            chatbot_figure = create_ai_chatbots_figure(site_data)
            trend_figure = create_ai_trend_figure(site_data)
            with ai_cols[0]:
                if chatbot_figure:
                    st.plotly_chart(chatbot_figure, use_container_width=True)
                else:
                    st.info("Aucune repartition chatbot disponible.")
            with ai_cols[1]:
                if trend_figure:
                    st.plotly_chart(trend_figure, use_container_width=True)
                else:
                    st.info("Aucune serie IA exploitable.")

        with tabs[6]:
            st.json(site_data)
            st.download_button(
                label="Telecharger le JSON du domaine",
                data=json.dumps(site_data, indent=2, ensure_ascii=False),
                file_name=f"similarweb_{selected_domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                key=f"json_domain_{key_prefix}",
            )


def render_batch_results(results: dict[str, dict], use_cache: bool, elapsed_time: float | None, key_prefix: str, title: str) -> None:
    success_rows, error_rows, valid_results = split_batch_results(results)
    summary = build_batch_context_summary(results, success_rows, error_rows, use_cache=use_cache, elapsed_time=elapsed_time)

    render_context_banner(summary, title=title)

    if error_rows:
        st.subheader("Erreurs")
        render_error_dataframe(error_rows, key=f"errors_{key_prefix}")

    if success_rows:
        st.subheader("Tableau benchmark")
        dataframe = render_batch_dataframe(success_rows, key=f"results_{key_prefix}")
        render_export_panel(dataframe, results, success_rows, error_rows, key_prefix=key_prefix)

        control_col_1, control_col_2 = st.columns(2)
        with control_col_1:
            show_portfolio = st.toggle(
                "Afficher les visualisations portefeuille",
                value=False,
                key=f"show_portfolio_{key_prefix}",
            )
        with control_col_2:
            show_explorer = st.toggle(
                "Afficher l'exploration domaine par domaine",
                value=False,
                key=f"show_explorer_{key_prefix}",
            )

        if show_portfolio:
            render_batch_portfolio_charts(dataframe)
        else:
            st.caption("Les visualisations portefeuille restent repliees par defaut pour accelerer l'affichage du lot.")

        if show_explorer:
            st.markdown("---")
            st.subheader("Explorer un domaine")
            render_domain_explorer(valid_results, key_prefix=f"{key_prefix}_domain")
        else:
            st.caption("L'exploration detaillee par domaine est chargee a la demande.")
    elif not error_rows:
        st.info("Aucun resultat a afficher.")


def analyze_batch_period(domains_list: list[str], period_start, period_end) -> None:
    start_datetime = datetime.combine(period_start, datetime.min.time())
    end_datetime = datetime.combine(period_end, datetime.max.time())
    rows = []
    missing_domains = 0

    progress_bar = st.progress(0)
    status_text = st.empty()

    for index, domain in enumerate(domains_list, 1):
        clean_domain = similar.extract_domain(domain)
        progress_bar.progress(index / len(domains_list))
        status_text.info(f"Analyse historique: {clean_domain} ({index}/{len(domains_list)})")
        history_entries = similar.get_history_for_domain(clean_domain, start_date=start_datetime, end_date=end_datetime)
        if history_entries:
            rows.append(build_period_analysis_row(clean_domain, history_entries, start_datetime, end_datetime))
        else:
            missing_domains += 1
            rows.append(
                {
                    "Domaine": clean_domain,
                    "Periode analysee": f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}",
                    "Nb points de collecte": 0,
                    "Source serie": "Historique local de snapshots",
                    "Dernier snapshot API": "N/A",
                    "Derniere periode donnee": "N/A",
                    "Statut": "Aucune donnee historique",
                }
            )

    progress_bar.progress(1.0)
    status_text.empty()

    dataframe = pd.DataFrame(rows)
    render_context_banner(
        {
            "total": len(domains_list),
            "success": len(domains_list) - missing_domains,
            "error": missing_domains,
            "use_cache": True,
            "latest_snapshot": dataframe["Dernier snapshot API"].dropna().astype(str).max() if "Dernier snapshot API" in dataframe.columns and not dataframe.empty else "N/A",
            "latest_period": dataframe["Derniere periode donnee"].dropna().astype(str).max() if "Derniere periode donnee" in dataframe.columns and not dataframe.empty else "N/A",
        },
        title="Analyse par periode",
    )
    st.caption("La comparaison porte sur les snapshots deja sauvegardes localement, pas sur une reinterrogation de l'API.")
    st.dataframe(dataframe, use_container_width=True, hide_index=True)

    csv_data = dataframe.to_csv(index=False, encoding="utf-8-sig")
    json_data = json.dumps(rows, indent=2, ensure_ascii=False)
    export_cols = st.columns(2)
    export_cols[0].download_button(
        label="Telecharger CSV",
        data=csv_data,
        file_name=f"similarweb_period_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )
    export_cols[1].download_button(
        label="Telecharger JSON",
        data=json_data,
        file_name=f"similarweb_period_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
    )


def clear_batch_state() -> None:
    for key in VALID_RESULT_SESSION_KEYS + ["domain_selector_batch_current_domain", "pdf_bytes_batch_current", "pdf_bytes_batch_previous"]:
        if key in st.session_state:
            del st.session_state[key]


batch_tab, single_tab, history_tab = st.tabs(["Traitement par lots", "Recherche unique", "Periodicite & historique"])

with batch_tab:
    st.header("Traitement par lots")
    st.caption("Le batch devient le point d'entree principal. Le moteur utilise un pipeline asynchrone avec concurrence controlee, tout en gardant une posture prudente face aux limites de l'API.")

    with st.form("batch_lookup_form"):
        st.subheader("1. Coller vos domaines")
        manual_input = st.text_area(
            "Liste de domaines",
            height=220,
            placeholder="example.com\ncompetitor.com\nanother-site.org",
            help="Un domaine par ligne, avec ou sans protocole. Cette saisie reste prioritaire sur l'import fichier.",
        )

        with st.expander("Importer un fichier (optionnel)", expanded=False):
            uploaded_file = st.file_uploader("Fichier CSV ou TXT", type=["csv", "txt"], key="batch_file_upload")
            st.caption("Le fichier n'est lu que si aucune liste manuelle n'est collee.")

        with st.expander("Configuration avancee", expanded=False):
            st.caption("Valeurs par defaut orientees stabilite. Reduire le delai augmente le risque de 403 si vous ne passez pas par des proxys.")
            config_col_1, config_col_2 = st.columns(2)
            with config_col_1:
                network_preset = st.selectbox(
                    "Preset reseau",
                    list(NETWORK_PRESETS.keys()),
                    index=0,
                    help="Les presets appliquent automatiquement un couple delai / concurrence.",
                )
                st.caption(NETWORK_PRESETS[network_preset]["description"])
                use_cache = st.checkbox("Utiliser le cache", value=True)
                chunk_size = st.number_input("Chunk size", min_value=10, max_value=500, value=100, step=10)
            with config_col_2:
                retry_count = st.number_input("Nombre de tentatives", min_value=1, max_value=3, value=DEFAULT_RETRY_COUNT)
                max_domains = st.number_input("Nombre maximum de domaines", min_value=1, max_value=10000, value=500, step=10)
                if network_preset == "Personnalise":
                    delay = st.slider("Delai cible entre requetes (secondes)", 1.0, 300.0, 60.0, 5.0)
                    max_concurrency = st.number_input("Concurrence max", min_value=1, max_value=5, value=1, step=1)
                else:
                    resolved_delay, resolved_concurrency = resolve_network_settings(network_preset, 60.0, 1)
                    st.metric("Delai applique", f"{resolved_delay:.1f}s")
                    st.metric("Concurrence appliquee", resolved_concurrency)
                    delay = resolved_delay
                    max_concurrency = resolved_concurrency

            analyze_period = st.checkbox(
                "Basculer en analyse historique sur une periode",
                value=False,
                help="Dans ce mode, l'outil lit l'historique local plutot que de relancer l'API.",
            )
            period_start = None
            period_end = None
            if analyze_period:
                period_col_1, period_col_2 = st.columns(2)
                with period_col_1:
                    period_start = st.date_input("Date de debut", value=datetime.now() - timedelta(days=30))
                with period_col_2:
                    period_end = st.date_input("Date de fin", value=datetime.now())
        launch_batch = st.form_submit_button("Lancer le traitement", type="primary", use_container_width=True)

    domains_list = [line.strip() for line in manual_input.splitlines() if line.strip()][: int(max_domains)]
    if domains_list:
        st.info(f"{len(domains_list)} domaine(s) detecte(s) dans la saisie manuelle.")
    elif uploaded_file is not None:
        st.caption("Aucun domaine colle. Le fichier sera utilise a la soumission.")
    else:
        st.info("Collez une liste de domaines pour lancer un lot rapidement. L'import fichier reste disponible si besoin.")

    if launch_batch:
        if not domains_list and uploaded_file is not None:
            try:
                domains_list = parse_uploaded_domains(uploaded_file, int(max_domains))
            except Exception as error:
                domains_list = []
                st.error(f"Lecture impossible: {error}")

        if analyze_period and period_start and period_end and period_start > period_end:
            st.error("La date de debut doit etre anterieure a la date de fin.")
        elif not domains_list:
            st.warning("Saisissez ou importez au moins un domaine pour lancer le traitement.")
        else:
            effective_delay, effective_concurrency = resolve_network_settings(network_preset, delay, int(max_concurrency))
            st.info(
                f"Temps estime: {estimate_runtime_label(len(domains_list), effective_delay)} pour {len(domains_list)} domaine(s). "
                f"Preset applique: {network_preset}."
            )
            clear_batch_state()
            if analyze_period and period_start and period_end:
                analyze_batch_period(domains_list, period_start, period_end)
            else:
                if use_proxies and not proxy_list:
                    st.warning("Option proxy activee sans proxy valide. Le lot partira sans proxy.")
                results, elapsed_time = run_batch_lookup(
                    domains_list,
                    effective_delay,
                    use_cache,
                    int(retry_count),
                    int(chunk_size),
                    proxy_list,
                    effective_concurrency,
                )
                st.session_state["batch_results"] = results
                st.session_state["batch_use_cache"] = use_cache
                st.session_state["batch_elapsed_time"] = elapsed_time
                success_rows, error_rows, _ = split_batch_results(results)
                st.session_state["batch_success_rows"] = success_rows
                st.session_state["batch_error_rows"] = error_rows

    st.subheader("2. Explorer")
    current_results = st.session_state.get("batch_results") or {}
    if current_results:
        render_batch_results(
            current_results,
            use_cache=st.session_state.get("batch_use_cache", True),
            elapsed_time=st.session_state.get("batch_elapsed_time"),
            key_prefix="batch_current",
            title="Resultat du dernier lot",
        )
    else:
        st.info("Aucun lot execute dans cette session.")

with single_tab:
    st.header("Recherche unique")
    st.caption("Lecture d'un domaine unique avec contexte de fraicheur, capture et modules API supplementaires.")
    input_col, button_col = st.columns([3, 1])
    with input_col:
        website_input = st.text_input(
            "URL ou domaine",
            placeholder="https://example.com ou example.com",
            help="Le moteur normalise l'entree avant l'appel API.",
        )
    with button_col:
        st.write("")
        st.write("")
        search_button = st.button("Analyser", type="primary", use_container_width=True)

    if search_button and not website_input:
        st.warning("Entrez un domaine ou une URL valide.")
    elif search_button and website_input:
        with st.spinner("Recuperation du snapshot en cours..."):
            result = run_single_lookup(website_input)
        if is_valid_result(result):
            render_domain_explorer({similar.extract_domain(website_input): result}, key_prefix="single", selected_domain=similar.extract_domain(website_input))
        elif isinstance(result, dict) and result.get("error"):
            st.error(get_user_facing_error_message(result))
            diagnostic = get_error_diagnostic(result)
            if diagnostic:
                st.caption(diagnostic)
        else:
            st.error("Aucune donnee exploitable retournee par l'API.")

with history_tab:
    st.header("Periodicite & historique")
    st.caption("Cette vue distingue clairement la date de collecte locale et la periode de donnee fournie par Similarweb.")

    all_domains = sorted(similar.get_all_domains_in_history())
    if not all_domains:
        st.info("Aucun historique disponible pour le moment. Les prochaines recherches valides seront stockees automatiquement.")
    else:
        selected_domain = st.selectbox("Domaine suivi", all_domains)
        history_entries = similar.get_history_for_domain(selected_domain)
        history_dataframe = build_history_dataframe(history_entries)

        render_context_banner(
            {
                "total": len(history_entries),
                "success": len(history_entries),
                "error": 0,
                "use_cache": True,
                "latest_snapshot": history_dataframe["Snapshot API"].iloc[-1] if not history_dataframe.empty else "N/A",
                "latest_period": history_dataframe["Periode donnee"].iloc[-1] if not history_dataframe.empty else "N/A",
            },
            title="Historique local",
        )
        st.caption("Serie = snapshots Similarweb enregistres localement au moment des collectes. Ce n'est pas une API de time series native.")

        history_subtab, comparison_subtab, raw_subtab = st.tabs(["Evolution", "Comparaison", "Donnees brutes"])

        with history_subtab:
            if history_dataframe.empty:
                st.info("Aucune serie disponible pour ce domaine.")
            else:
                chart_cols = st.columns(3)
                visits_chart = create_history_metric_figure(history_dataframe, "Visites mensuelles", "Evolution des visites", color=PRIMARY_BLUE)
                rank_chart = create_history_metric_figure(history_dataframe, "Classement global", "Evolution du classement", color=WARNING_ORANGE, reverse_y=True)
                bounce_chart = create_history_metric_figure(history_dataframe, "Taux de rebond (%)", "Evolution du bounce rate", color=SUCCESS_GREEN)

                with chart_cols[0]:
                    if visits_chart:
                        st.plotly_chart(visits_chart, use_container_width=True)
                with chart_cols[1]:
                    if rank_chart:
                        st.plotly_chart(rank_chart, use_container_width=True)
                with chart_cols[2]:
                    if bounce_chart:
                        st.plotly_chart(bounce_chart, use_container_width=True)

                render_history_dataframe(history_dataframe, key="history_overview_table")
                st.download_button(
                    label="Telecharger l'historique CSV",
                    data=history_dataframe.to_csv(index=False, encoding="utf-8-sig"),
                    file_name=f"similarweb_history_{selected_domain}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )

        with comparison_subtab:
            periods = sorted({entry.get("period", entry.get("date", "")[:7]) for entry in history_entries if entry.get("period") or entry.get("date")})
            if len(periods) < 2:
                st.info("Au moins deux periodes sont necessaires pour une comparaison.")
            else:
                compare_col_1, compare_col_2 = st.columns(2)
                with compare_col_1:
                    period_1 = st.selectbox("Periode 1", periods, index=0)
                with compare_col_2:
                    period_2 = st.selectbox("Periode 2", periods, index=min(1, len(periods) - 1))

                if period_1 != period_2:
                    comparison = similar.compare_periods(selected_domain, period_1, period_2)
                    if comparison:
                        if "visits" in comparison["changes"]:
                            visits_change = comparison["changes"]["visits"]
                            cols = st.columns(3)
                            cols[0].metric(f"Visites {period_1}", f"{int(visits_change['period1']):,}".replace(",", " "))
                            cols[1].metric(f"Visites {period_2}", f"{int(visits_change['period2']):,}".replace(",", " "))
                            cols[2].metric("Delta", f"{int(visits_change['change']):,}".replace(",", " "), delta=f"{visits_change['change_percent']:+.2f}%")

                        if "rank" in comparison["changes"]:
                            rank_change = comparison["changes"]["rank"]
                            cols = st.columns(3)
                            cols[0].metric(f"Classement {period_1}", f"#{rank_change['period1']}")
                            cols[1].metric(f"Classement {period_2}", f"#{rank_change['period2']}")
                            cols[2].metric("Delta", f"#{rank_change['period2']}", delta=f"{rank_change['change']:+d}")

                        st.download_button(
                            label="Telecharger la comparaison JSON",
                            data=json.dumps(comparison, indent=2, ensure_ascii=False),
                            file_name=f"similarweb_comparison_{selected_domain}_{period_1}_vs_{period_2}.json",
                            mime="application/json",
                        )
                    else:
                        st.warning("Comparaison impossible pour ces periodes.")

        with raw_subtab:
            filter_cols = st.columns(2)
            with filter_cols[0]:
                filter_start = st.date_input("Date de debut", value=datetime.now() - timedelta(days=30), key="history_filter_start")
            with filter_cols[1]:
                filter_end = st.date_input("Date de fin", value=datetime.now(), key="history_filter_end")

            filtered_entries = [
                entry
                for entry in history_entries
                if filter_start <= datetime.fromisoformat(entry["timestamp"]).date() <= filter_end
            ]
            st.info(f"{len(filtered_entries)} entree(s) historiques dans la fenetre selectionnee.")
            for entry in reversed(filtered_entries):
                label = f"{entry.get('date', 'N/A')} | periode {entry.get('period', 'N/A')} | collecte {entry.get('timestamp', '')[:19]}"
                with st.expander(label):
                    st.json(entry.get("data", {}))

            if filtered_entries:
                st.download_button(
                    label="Telecharger le JSON filtre",
                    data=json.dumps(filtered_entries, indent=2, ensure_ascii=False),
                    file_name=f"similarweb_history_{selected_domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                )

with st.expander("Mode d'emploi"):
    st.markdown(
        """
        - **Recherche unique**: lire un snapshot complet, sa capture, ses mots-cles et ses signaux IA.
        - **Traitement par lots**: configurer, lancer, puis explorer un benchmark unifie avec exports CSV / JSON / PDF.
        - **Periodicite & historique**: analyser les snapshots sauvegardes localement dans le temps.
        - **Important**: `Snapshot API` represente la fraicheur du payload Similarweb. `Periode donnee` represente le mois du dernier point de la serie de visites.
        """
    )
