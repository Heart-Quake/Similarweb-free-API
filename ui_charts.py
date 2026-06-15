from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ui_builders import get_ai_traffic_summary, get_top_country_rows, get_top_keyword_rows

PRIMARY_BLUE = "#2563eb"
PRIMARY_BLUE_LIGHT = "#93c5fd"
SUCCESS_GREEN = "#0f766e"
WARNING_ORANGE = "#f59e0b"
DANGER_RED = "#dc2626"
NEUTRAL_GREY = "#94a3b8"
SURFACE = "#f8fafc"

TRAFFIC_SOURCE_ORDER = ("Direct", "Search", "Social", "Mail", "Paid", "Referrals", "Paid Referrals")
TRAFFIC_SOURCE_LABELS = {
    "Direct": "Direct",
    "Search": "Recherche",
    "Social": "Social",
    "Mail": "Email",
    "Paid": "Payant",
    "Referrals": "Referents",
    "Paid Referrals": "Referents payants",
    "Autres": "Autres",
}


def _apply_chart_layout(fig: go.Figure, title: str, height: int = 360) -> go.Figure:
    fig.update_layout(
        title=title,
        height=height,
        template="plotly_white",
        font=dict(size=12, color="#0f172a"),
        title_font=dict(size=16, color="#0f172a"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=70, b=20),
    )
    return fig


def normalize_traffic_sources(sources: dict, min_pct: float = 2.0) -> pd.DataFrame:
    if not sources or not isinstance(sources, dict):
        return pd.DataFrame(columns=["Source", "Pourcentage"])

    rows = []
    for key, value in sources.items():
        try:
            pct = float(value) * 100.0
        except (TypeError, ValueError):
            continue
        if pct > 0:
            rows.append({"Source": key, "Pourcentage": pct})

    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return dataframe

    small_mask = dataframe["Pourcentage"] < float(min_pct)
    other_sum = float(dataframe.loc[small_mask, "Pourcentage"].sum())
    dataframe = dataframe.loc[~small_mask].copy()
    if other_sum > 0:
        dataframe = pd.concat(
            [dataframe, pd.DataFrame([{"Source": "Autres", "Pourcentage": other_sum}])],
            ignore_index=True,
        )

    order = [label for label in TRAFFIC_SOURCE_ORDER if label in set(dataframe["Source"])]
    if "Autres" in set(dataframe["Source"]):
        order.append("Autres")
    dataframe["Sort"] = dataframe["Source"].apply(lambda value: order.index(value) if value in order else 999)
    dataframe["Source label"] = dataframe["Source"].map(TRAFFIC_SOURCE_LABELS).fillna(dataframe["Source"])
    dataframe = dataframe.sort_values(["Sort", "Pourcentage"], ascending=[True, False]).drop(columns=["Sort"])
    return dataframe


def build_visits_dataframe(site_data: dict) -> pd.DataFrame:
    visits = site_data.get("EstimatedMonthlyVisits") if isinstance(site_data, dict) else None
    if not isinstance(visits, dict) or not visits:
        return pd.DataFrame(columns=["Date", "Visites"])

    dataframe = pd.DataFrame(list(visits.items()), columns=["Date", "Visites"])
    dataframe["Date"] = pd.to_datetime(dataframe["Date"], errors="coerce")
    dataframe["Visites"] = pd.to_numeric(dataframe["Visites"], errors="coerce")
    dataframe = dataframe.dropna().sort_values("Date")
    return dataframe


def create_visits_trend_figure(site_data: dict, title: str = "Tendance des visites mensuelles") -> go.Figure | None:
    dataframe = build_visits_dataframe(site_data)
    if dataframe.empty:
        return None

    figure = px.line(
        dataframe,
        x="Date",
        y="Visites",
        markers=True,
        color_discrete_sequence=[PRIMARY_BLUE],
    )
    figure.update_traces(line_width=3, marker_size=9)
    last_row = dataframe.iloc[-1]
    figure.add_annotation(
        x=last_row["Date"],
        y=last_row["Visites"],
        text=f"Dernier point: {int(last_row['Visites']):,}".replace(",", " "),
        showarrow=True,
        arrowcolor=PRIMARY_BLUE,
        ay=-45,
        bgcolor="white",
    )
    figure.update_yaxes(title="Visites", separatethousands=True)
    figure.update_xaxes(title="Periode")
    return _apply_chart_layout(figure, title)


def create_traffic_sources_figure(site_data: dict, title: str = "Mix des sources de trafic") -> go.Figure | None:
    dataframe = normalize_traffic_sources(site_data.get("TrafficSources") or {})
    if dataframe.empty:
        return None

    figure = px.pie(
        dataframe,
        values="Pourcentage",
        names="Source label",
        color_discrete_sequence=[PRIMARY_BLUE, SUCCESS_GREEN, WARNING_ORANGE, "#14b8a6", "#f97316", "#64748b", PRIMARY_BLUE_LIGHT],
    )
    figure.update_traces(hole=0.55, textinfo="percent", hovertemplate="<b>%{label}</b><br>%{value:.2f}%<extra></extra>")
    return _apply_chart_layout(figure, title, height=400)


def create_top_countries_figure(site_data: dict, title: str = "Top pays") -> go.Figure | None:
    rows = get_top_country_rows(site_data, limit=5)
    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return None

    dataframe = dataframe.sort_values("Part du trafic (%)", ascending=True)
    figure = px.bar(
        dataframe,
        x="Part du trafic (%)",
        y="Code",
        orientation="h",
        text="Part du trafic (%)",
        color_discrete_sequence=[PRIMARY_BLUE],
    )
    figure.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    figure.update_xaxes(title="Part du trafic (%)")
    figure.update_yaxes(title="Pays")
    return _apply_chart_layout(figure, title)


def create_engagement_figure(site_data: dict, title: str = "Engagement") -> go.Figure | None:
    engagements = site_data.get("Engagments") if isinstance(site_data.get("Engagments"), dict) else {}
    rows = []
    if engagements.get("BounceRate") is not None:
        rows.append({"Metrique": "Taux de rebond (%)", "Valeur": float(engagements.get("BounceRate", 0)) * 100, "Couleur": WARNING_ORANGE})
    if engagements.get("PagePerVisit") is not None:
        rows.append({"Metrique": "Pages / visite", "Valeur": float(engagements.get("PagePerVisit", 0)), "Couleur": PRIMARY_BLUE})
    if engagements.get("TimeOnSite") is not None:
        rows.append({"Metrique": "Duree (min)", "Valeur": float(engagements.get("TimeOnSite", 0)) / 60, "Couleur": SUCCESS_GREEN})

    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return None

    figure = go.Figure(
        data=[
            go.Bar(
                x=dataframe["Metrique"],
                y=dataframe["Valeur"],
                marker_color=dataframe["Couleur"],
                text=[f"{value:.2f}" for value in dataframe["Valeur"]],
                textposition="outside",
            )
        ]
    )
    figure.update_xaxes(title="")
    figure.update_yaxes(title="Valeur")
    return _apply_chart_layout(figure, title)


def create_history_metric_figure(
    dataframe: pd.DataFrame,
    metric_column: str,
    title: str,
    color: str = PRIMARY_BLUE,
    reverse_y: bool = False,
) -> go.Figure | None:
    if dataframe.empty or metric_column not in dataframe.columns:
        return None
    series = dataframe[["Date collecte", metric_column]].copy().dropna()
    if series.empty:
        return None

    figure = px.line(
        series,
        x="Date collecte",
        y=metric_column,
        markers=True,
        color_discrete_sequence=[color],
    )
    figure.update_traces(line_width=3, marker_size=8)
    figure.update_xaxes(title="Date de collecte")
    figure.update_yaxes(title=metric_column, autorange="reversed" if reverse_y else True, separatethousands=True)
    return _apply_chart_layout(figure, title)


def create_top_keywords_figure(site_data: dict, title: str = "Top mots-cles") -> go.Figure | None:
    rows = get_top_keyword_rows(site_data, limit=10)
    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return None

    dataframe["Volume"] = pd.to_numeric(dataframe["Volume"], errors="coerce")
    dataframe = dataframe.dropna(subset=["Volume"]).sort_values("Volume", ascending=True)
    if dataframe.empty:
        return None

    figure = px.bar(
        dataframe,
        x="Volume",
        y="Mot-cle",
        orientation="h",
        color_discrete_sequence=[PRIMARY_BLUE],
        text="Volume",
    )
    figure.update_traces(texttemplate="%{text}", textposition="outside")
    figure.update_xaxes(title="Volume")
    figure.update_yaxes(title="")
    return _apply_chart_layout(figure, title, height=440)


def create_ai_chatbots_figure(site_data: dict, title: str = "Trafic referent IA") -> go.Figure | None:
    ai_summary = get_ai_traffic_summary(site_data)
    dataframe = pd.DataFrame(ai_summary["top_chatbots"])
    if dataframe.empty:
        return None

    dataframe = dataframe.dropna(subset=["Valeur"]).sort_values("Valeur", ascending=True)
    if dataframe.empty:
        return None

    figure = px.bar(
        dataframe,
        x="Valeur",
        y="Chatbot",
        orientation="h",
        color_discrete_sequence=[SUCCESS_GREEN],
        text="Valeur",
    )
    figure.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    figure.update_xaxes(title="Poids relatif")
    figure.update_yaxes(title="")
    return _apply_chart_layout(figure, title, height=360)


def create_ai_trend_figure(site_data: dict, title: str = "Evolution du trafic IA") -> go.Figure | None:
    ai_summary = get_ai_traffic_summary(site_data)
    dataframe = pd.DataFrame(ai_summary["history"])
    if dataframe.empty:
        return None

    dataframe["Date"] = pd.to_datetime(dataframe["Date"], errors="coerce")
    dataframe["Valeur"] = pd.to_numeric(dataframe["Valeur"], errors="coerce")
    dataframe = dataframe.dropna().sort_values("Date")
    if dataframe.empty:
        return None

    figure = px.line(
        dataframe,
        x="Date",
        y="Valeur",
        color="Chatbot",
        markers=True,
    )
    figure.update_xaxes(title="Periode")
    figure.update_yaxes(title="Poids relatif")
    return _apply_chart_layout(figure, title, height=420)
