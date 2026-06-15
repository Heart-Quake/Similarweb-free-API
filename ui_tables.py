from __future__ import annotations

import pandas as pd
import streamlit as st

from ui_builders import BATCH_COLUMN_ORDER, has_unique_visitors_values


def prepare_batch_dataframe(rows: list[dict], sort_by: str = "Visites mensuelles") -> pd.DataFrame:
    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return dataframe

    ordered_columns = [column for column in BATCH_COLUMN_ORDER if column in dataframe.columns]
    remaining_columns = [column for column in dataframe.columns if column not in ordered_columns]
    dataframe = dataframe[ordered_columns + remaining_columns]

    if not has_unique_visitors_values(dataframe) and "Visites uniques" in dataframe.columns:
        dataframe = dataframe.drop(columns=["Visites uniques"])

    if sort_by in dataframe.columns:
        dataframe = dataframe.sort_values(sort_by, ascending=False, na_position="last")

    return dataframe


def prepare_error_dataframe(rows: list[dict]) -> pd.DataFrame:
    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return dataframe
    expected_columns = [
        column
        for column in ["Domaine", "Source", "Type d'erreur", "Message d'erreur", "Diagnostic", "Detail technique"]
        if column in dataframe.columns
    ]
    remaining_columns = [column for column in dataframe.columns if column not in expected_columns]
    return dataframe[expected_columns + remaining_columns]


def get_batch_column_config(dataframe: pd.DataFrame) -> dict:
    config = {}
    if "Domaine" in dataframe.columns:
        config["Domaine"] = st.column_config.TextColumn("Domaine", width="medium")
    if "Source" in dataframe.columns:
        config["Source"] = st.column_config.TextColumn("Source", width="small")
    if "Snapshot API" in dataframe.columns:
        config["Snapshot API"] = st.column_config.TextColumn("Snapshot API", width="small")
    if "Periode donnee" in dataframe.columns:
        config["Periode donnee"] = st.column_config.TextColumn("Periode donnee", width="small")
    if "Visites (M)" in dataframe.columns:
        config["Visites (M)"] = st.column_config.NumberColumn("Visites (M)", format="%.2f")
    if "Visites mensuelles" in dataframe.columns:
        config["Visites mensuelles"] = st.column_config.NumberColumn("Visites mensuelles", format="%d")
    if "Visites uniques" in dataframe.columns:
        config["Visites uniques"] = st.column_config.NumberColumn("Visites uniques", format="%d")
    if "Pages par visite" in dataframe.columns:
        config["Pages par visite"] = st.column_config.NumberColumn("Pages / visite", format="%.2f")
    if "Duree (min)" in dataframe.columns:
        config["Duree (min)"] = st.column_config.NumberColumn("Duree (min)", format="%.2f")
    if "Taux de rebond (%)" in dataframe.columns:
        config["Taux de rebond (%)"] = st.column_config.ProgressColumn("Bounce rate", min_value=0.0, max_value=100.0, format="%.2f%%")
    if "Trafic direct (%)" in dataframe.columns:
        config["Trafic direct (%)"] = st.column_config.ProgressColumn("Direct", min_value=0.0, max_value=100.0, format="%.2f%%")
    if "Trafic organique (%)" in dataframe.columns:
        config["Trafic organique (%)"] = st.column_config.ProgressColumn("Organic", min_value=0.0, max_value=100.0, format="%.2f%%")
    if "Trafic payant (%)" in dataframe.columns:
        config["Trafic payant (%)"] = st.column_config.ProgressColumn("Paid", min_value=0.0, max_value=100.0, format="%.2f%%")
    if "Trafic reseaux sociaux (%)" in dataframe.columns:
        config["Trafic reseaux sociaux (%)"] = st.column_config.ProgressColumn("Social", min_value=0.0, max_value=100.0, format="%.2f%%")
    if "Trafic email (%)" in dataframe.columns:
        config["Trafic email (%)"] = st.column_config.ProgressColumn("Email", min_value=0.0, max_value=100.0, format="%.2f%%")
    if "Classement global" in dataframe.columns:
        config["Classement global"] = st.column_config.NumberColumn("Classement global", format="%d")
    if "Description" in dataframe.columns:
        config["Description"] = st.column_config.TextColumn("Description", width="large")
    return config


def render_batch_dataframe(rows: list[dict], key: str = "batch_table") -> pd.DataFrame:
    dataframe = prepare_batch_dataframe(rows)
    if dataframe.empty:
        st.info("Aucune ligne disponible.")
        return dataframe

    st.dataframe(
        dataframe,
        use_container_width=True,
        hide_index=True,
        column_config=get_batch_column_config(dataframe),
        key=key,
    )
    return dataframe


def render_error_dataframe(rows: list[dict], key: str = "error_table") -> pd.DataFrame:
    dataframe = prepare_error_dataframe(rows)
    if dataframe.empty:
        return dataframe
    st.dataframe(dataframe, use_container_width=True, hide_index=True, key=key)
    return dataframe


def render_keywords_table(rows: list[dict], key: str = "keywords_table") -> pd.DataFrame:
    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        st.info("Aucun mot-cle disponible.")
        return dataframe

    dataframe = dataframe.sort_values(["Valeur estimee", "Volume"], ascending=[False, False], na_position="last")
    st.dataframe(
        dataframe,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Mot-cle": st.column_config.TextColumn("Mot-cle", width="medium"),
            "Volume": st.column_config.NumberColumn("Volume", format="%d"),
            "CPC": st.column_config.NumberColumn("CPC", format="%.2f"),
            "Valeur estimee": st.column_config.NumberColumn("Valeur estimee", format="%d"),
        },
        key=key,
    )
    return dataframe


def render_history_dataframe(dataframe: pd.DataFrame, key: str = "history_table") -> None:
    if dataframe.empty:
        st.info("Aucune donnee historique disponible.")
        return

    st.dataframe(
        dataframe,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Date collecte": st.column_config.DatetimeColumn("Date collecte", format="DD/MM/YYYY HH:mm"),
            "Visites mensuelles": st.column_config.NumberColumn("Visites mensuelles", format="%d"),
            "Classement global": st.column_config.NumberColumn("Classement global", format="%d"),
            "Taux de rebond (%)": st.column_config.NumberColumn("Bounce rate", format="%.2f"),
            "Snapshot API": st.column_config.TextColumn("Snapshot API", width="small"),
            "Periode donnee": st.column_config.TextColumn("Periode donnee", width="small"),
            "Source serie": st.column_config.TextColumn("Source serie", width="medium"),
        },
        key=key,
    )
