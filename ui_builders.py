from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from config import (
    CACHE_STATUS_KEY,
    CACHE_STATUS_STALE,
    RESULT_SOURCE_KEY,
    SOURCE_API_LIVE,
    SOURCE_CACHE_STALE,
    SOURCE_SIMILARWEB_BLOCKED,
    is_provider_blocked_payload,
    is_stale_fallback_payload,
)

VALID_RESULT_KEYS = {
    "EstimatedMonthlyVisits",
    "GlobalRank",
    "SiteName",
    "Domain",
    "Engagments",
    "TrafficSources",
    "TopCountryShares",
    "Category",
}

BATCH_COLUMN_ORDER = [
    "Domaine",
    "Source",
    "Snapshot API",
    "Periode donnee",
    "Visites (M)",
    "Visites mensuelles",
    "Visites uniques",
    "Pages par visite",
    "Duree (min)",
    "Taux de rebond (%)",
    "Trafic direct (%)",
    "Trafic organique (%)",
    "Trafic payant (%)",
    "Trafic reseaux sociaux (%)",
    "Trafic email (%)",
    "Classement global",
    "Classement Pays",
    "Classement Categorie",
    "Categorie",
    "Top 3 Pays",
    "Top Mots-cles",
    "Description",
]

PRIMARY_BATCH_COLUMNS = [
    "Domaine",
    "Snapshot API",
    "Periode donnee",
    "Visites (M)",
    "Visites mensuelles",
    "Pages par visite",
    "Duree (min)",
    "Taux de rebond (%)",
    "Trafic direct (%)",
    "Trafic organique (%)",
    "Trafic payant (%)",
    "Classement global",
    "Categorie",
]


def extract_domain(website: str) -> str:
    parsed = urlparse(website)
    domain = parsed.netloc if parsed.netloc else parsed.path.split("/")[0]
    domain = domain.replace("www.", "")
    return domain.split("/")[0].split("?")[0].lower().strip()


def parse_int_value(value: Any) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_float_value(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_category_name(value: Any) -> str:
    if not value:
        return "N/A"
    return str(value).replace("_", " ").title()


def get_site_name(site_data: dict[str, Any], fallback: str) -> str:
    return site_data.get("SiteName") or site_data.get("Domain") or fallback


def get_snapshot_datetime(site_data: dict[str, Any]) -> datetime | None:
    snapshot = site_data.get("SnapshotDate")
    if not snapshot:
        return None
    try:
        return datetime.fromisoformat(str(snapshot).replace("Z", "+00:00"))
    except ValueError:
        return None


def get_snapshot_label(site_data: dict[str, Any]) -> str:
    snapshot_dt = get_snapshot_datetime(site_data)
    return snapshot_dt.strftime("%Y-%m") if snapshot_dt else "N/A"


def get_latest_data_period(site_data: dict[str, Any]) -> str:
    visits = site_data.get("EstimatedMonthlyVisits")
    if isinstance(visits, dict) and visits:
        try:
            latest_key = sorted(visits.keys())[-1]
            latest_date = pd.to_datetime(latest_key, errors="coerce")
            if pd.notna(latest_date):
                return latest_date.strftime("%Y-%m")
            return str(latest_key)[:7]
        except Exception:
            pass

    engagements = site_data.get("Engagments")
    if isinstance(engagements, dict):
        month = parse_int_value(engagements.get("Month"))
        year = parse_int_value(engagements.get("Year"))
        if month and year:
            return f"{year:04d}-{month:02d}"

    snapshot_label = get_snapshot_label(site_data)
    return snapshot_label if snapshot_label != "N/A" else "N/A"


def get_latest_monthly_visits(site_data: dict[str, Any]) -> int | None:
    visits = site_data.get("EstimatedMonthlyVisits")
    if isinstance(visits, dict):
        if not visits:
            return None
        try:
            latest_key = sorted(visits.keys())[-1]
            return parse_int_value(visits.get(latest_key))
        except Exception:
            for value in reversed(list(visits.values())):
                parsed = parse_int_value(value)
                if parsed is not None:
                    return parsed
            return None
    return parse_int_value(visits)


def get_unique_visitors(site_data: dict[str, Any]) -> int | None:
    unique_keys = (
        "UniqueVisitors",
        "MonthlyUniqueVisitors",
        "UniqueMonthlyVisitors",
        "DeduplicatedVisitors",
        "DeduplicatedAudience",
        "UniqueVisits",
    )

    for key in unique_keys:
        parsed = parse_int_value(site_data.get(key))
        if parsed is not None:
            return parsed

    engagements = site_data.get("Engagments")
    if isinstance(engagements, dict):
        for key in unique_keys:
            parsed = parse_int_value(engagements.get(key))
            if parsed is not None:
                return parsed

    return None


def get_global_rank(site_data: dict[str, Any]) -> int | None:
    rank = site_data.get("GlobalRank")
    if isinstance(rank, dict):
        return parse_int_value(rank.get("Rank"))
    return parse_int_value(rank)


def get_country_rank_label(site_data: dict[str, Any]) -> str:
    country_rank = site_data.get("CountryRank")
    if not isinstance(country_rank, dict):
        return "N/A"
    rank_value = parse_int_value(country_rank.get("Rank"))
    country_code = country_rank.get("CountryCode") or country_rank.get("Country")
    if rank_value is None:
        return "N/A"
    if country_code:
        return f"#{rank_value} ({country_code})"
    return f"#{rank_value}"


def get_category_rank_label(site_data: dict[str, Any]) -> str:
    category_rank = site_data.get("CategoryRank")
    if not isinstance(category_rank, dict):
        return "N/A"
    rank_value = parse_int_value(category_rank.get("Rank"))
    category_name = clean_category_name(category_rank.get("Category"))
    if rank_value is None:
        return "N/A"
    if category_name != "N/A":
        return f"#{rank_value} ({category_name})"
    return f"#{rank_value}"


def get_top_country_rows(site_data: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in (site_data.get("TopCountryShares") or [])[:limit]:
        rows.append(
            {
                "Pays": item.get("Country") or item.get("CountryCode") or "N/A",
                "Code": item.get("CountryCode") or "N/A",
                "Part du trafic (%)": round((parse_float_value(item.get("Value")) or 0.0) * 100, 2),
            }
        )
    return rows


def get_top_country_summary(site_data: dict[str, Any], limit: int = 3) -> str:
    rows = get_top_country_rows(site_data, limit=limit)
    if not rows:
        return "N/A"
    return ", ".join(f"{row['Code']}: {row['Part du trafic (%)']:.1f}%" for row in rows)


def get_top_keyword_rows(site_data: dict[str, Any], limit: int | None = None) -> list[dict[str, Any]]:
    keywords = site_data.get("TopKeywords") or []
    rows: list[dict[str, Any]] = []
    for item in keywords[:limit] if limit else keywords:
        rows.append(
            {
                "Mot-cle": item.get("Name") or "N/A",
                "Volume": parse_int_value(item.get("Volume")),
                "CPC": parse_float_value(item.get("Cpc")),
                "Valeur estimee": parse_int_value(item.get("EstimatedValue")),
            }
        )
    return rows


def get_top_keyword_summary(site_data: dict[str, Any], limit: int = 5) -> str:
    rows = get_top_keyword_rows(site_data, limit=limit)
    keywords = [row["Mot-cle"] for row in rows if row.get("Mot-cle") and row["Mot-cle"] != "N/A"]
    return ", ".join(keywords) if keywords else "N/A"


def get_ai_traffic_summary(site_data: dict[str, Any]) -> dict[str, Any]:
    ai_data = site_data.get("AiTrafficDetails")
    if not isinstance(ai_data, dict) or not ai_data:
        return {
            "total_visits": None,
            "referral_share_pct": None,
            "top_chatbots": [],
            "history": [],
            "prompts": [],
        }

    traffic_data = ai_data.get("Traffic") if isinstance(ai_data.get("Traffic"), dict) else {}
    distribution = traffic_data.get("Distribution") if isinstance(traffic_data, dict) else {}
    prompts_data = ai_data.get("TopPrompts") if isinstance(ai_data.get("TopPrompts"), dict) else {}

    top_chatbots = []
    for item in (distribution.get("Chatbots") or [])[:6]:
        top_chatbots.append(
            {
                "Chatbot": item.get("Name") or "N/A",
                "Valeur": parse_float_value(item.get("Value")),
            }
        )

    history_rows = []
    for chatbot in distribution.get("Chart") or []:
        chatbot_name = chatbot.get("Name") or "N/A"
        for point in chatbot.get("History") or []:
            history_rows.append(
                {
                    "Chatbot": chatbot_name,
                    "Date": point.get("Date"),
                    "Valeur": parse_float_value(point.get("Value")),
                }
            )

    prompts = prompts_data.get("Prompts") or []

    return {
        "total_visits": parse_float_value(ai_data.get("TotalVisits")),
        "referral_share_pct": round((parse_float_value(ai_data.get("ReferralTraffic")) or 0.0) * 100, 3)
        if ai_data.get("ReferralTraffic") is not None
        else None,
        "top_chatbots": top_chatbots,
        "history": history_rows,
        "prompts": prompts,
    }


def get_large_screenshot_url(site_data: dict[str, Any]) -> str | None:
    screenshot_url = site_data.get("LargeScreenshot")
    return str(screenshot_url) if screenshot_url else None


def is_valid_result(data: Any) -> bool:
    if not data or isinstance(data, bool) or not isinstance(data, dict):
        return False
    if "error" in data:
        return False
    return any(key in data for key in VALID_RESULT_KEYS)


def get_result_source_label(data: Any) -> str:
    if not isinstance(data, dict):
        return "N/A"
    explicit_source = data.get(RESULT_SOURCE_KEY)
    if explicit_source:
        return str(explicit_source)
    if data.get(CACHE_STATUS_KEY) == CACHE_STATUS_STALE:
        return SOURCE_CACHE_STALE
    if "error" in data and is_provider_blocked_payload(data):
        return SOURCE_SIMILARWEB_BLOCKED
    return SOURCE_API_LIVE


def should_save_to_history(data: Any) -> bool:
    return is_valid_result(data) and not is_stale_fallback_payload(data)


def extract_error_message(data: Any) -> str:
    if not data or isinstance(data, bool):
        return "Aucune donnee retournee"
    if isinstance(data, dict) and "error" in data:
        return str(data.get("error") or "Erreur inconnue")
    if isinstance(data, dict):
        return "Donnees incompletes ou invalides"
    return f"Format inattendu: {type(data).__name__}"


def is_rate_limited_result(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    status_code = parse_int_value(data.get("status_code"))
    error_message = extract_error_message(data)
    return (
        status_code in {403, 429}
        or error_message.startswith("HTTP 403")
        or error_message.startswith("HTTP 429")
        or is_provider_blocked_payload(data)
    )


def is_global_rate_limit_result(data: Any) -> bool:
    return is_provider_blocked_payload(data) or extract_error_message(data).startswith("Global rate limit detected")


def get_error_label(data: Any) -> str:
    error_message = extract_error_message(data)
    status_code = parse_int_value(data.get("status_code")) if isinstance(data, dict) else None

    if is_global_rate_limit_result(data):
        return "Blocage global Similarweb"
    if is_rate_limited_result(data):
        return "Blocage Similarweb"
    if status_code == 404 or error_message == "Domain not found":
        return "Domaine introuvable"
    if error_message == "Aucune donnee retournee":
        return "Aucune donnee"
    return "Erreur de collecte"


def get_error_diagnostic(data: Any) -> str | None:
    error_message = extract_error_message(data)
    status_code = parse_int_value(data.get("status_code")) if isinstance(data, dict) else None

    if is_global_rate_limit_result(data):
        return "Similarweb a renvoye plusieurs 403/429 consecutifs. Le lot a ete interrompu pour eviter des requetes inutiles."
    if is_rate_limited_result(data):
        return "Similarweb bloque actuellement cette session ou cette IP. Le domaine n'est pas necessairement en cause."
    if status_code == 404 or error_message == "Domain not found":
        return "Le domaine n'apparait pas dans le payload accessible depuis l'endpoint gratuit Similarweb."
    return None


def get_user_facing_error_message(data: Any) -> str:
    error_message = extract_error_message(data)

    if is_global_rate_limit_result(data):
        return "Blocage global Similarweb detecte. Le lot a ete coupe pour eviter des requetes inutiles."
    if is_rate_limited_result(data):
        return "Similarweb bloque actuellement cette requete. Le domaine n'est pas necessairement en cause."
    if get_error_label(data) == "Domaine introuvable":
        return "Le domaine est introuvable ou non couvert par le payload Similarweb."
    return error_message


def build_error_row(domain: str, data: Any) -> dict[str, Any]:
    technical_message = extract_error_message(data)
    user_message = get_user_facing_error_message(data)
    row = {
        "Domaine": domain,
        "Source": get_result_source_label(data),
        "Type d'erreur": get_error_label(data),
        "Message d'erreur": user_message,
    }
    diagnostic = get_error_diagnostic(data)
    if diagnostic:
        row["Diagnostic"] = diagnostic
    if technical_message != user_message:
        row["Detail technique"] = technical_message
    return row


def build_domain_row(domain: str, site_data: dict[str, Any]) -> dict[str, Any]:
    latest_visits = get_latest_monthly_visits(site_data)
    unique_visitors = get_unique_visitors(site_data)
    engagements = site_data.get("Engagments") if isinstance(site_data.get("Engagments"), dict) else {}
    traffic_sources = site_data.get("TrafficSources") if isinstance(site_data.get("TrafficSources"), dict) else {}

    bounce_rate = parse_float_value(engagements.get("BounceRate"))
    pages_per_visit = parse_float_value(engagements.get("PagePerVisit"))
    time_on_site = parse_float_value(engagements.get("TimeOnSite"))
    direct = parse_float_value(traffic_sources.get("Direct"))
    organic = parse_float_value(traffic_sources.get("Search"))
    social = parse_float_value(traffic_sources.get("Social"))
    email = parse_float_value(traffic_sources.get("Mail"))
    paid = (parse_float_value(traffic_sources.get("Paid")) or 0.0) + (
        parse_float_value(traffic_sources.get("Paid Referrals")) or 0.0
    )

    description = site_data.get("Description") or "N/A"
    if description != "N/A" and len(description) > 110:
        description = description[:107].rstrip() + "..."

    return {
        "Domaine": domain,
        "Source": get_result_source_label(site_data),
        "Snapshot API": get_snapshot_label(site_data),
        "Periode donnee": get_latest_data_period(site_data),
        "Visites (M)": round(latest_visits / 1_000_000, 2) if latest_visits else 0.0,
        "Visites mensuelles": latest_visits,
        "Visites uniques": unique_visitors,
        "Pages par visite": round(pages_per_visit, 2) if pages_per_visit is not None else None,
        "Duree (min)": round((time_on_site or 0.0) / 60, 2) if time_on_site is not None else None,
        "Taux de rebond (%)": round((bounce_rate or 0.0) * 100, 2) if bounce_rate is not None else None,
        "Trafic direct (%)": round((direct or 0.0) * 100, 2) if direct is not None else None,
        "Trafic organique (%)": round((organic or 0.0) * 100, 2) if organic is not None else None,
        "Trafic payant (%)": round(paid * 100, 2) if paid is not None else None,
        "Trafic reseaux sociaux (%)": round((social or 0.0) * 100, 2) if social is not None else None,
        "Trafic email (%)": round((email or 0.0) * 100, 2) if email is not None else None,
        "Classement global": get_global_rank(site_data),
        "Classement Pays": get_country_rank_label(site_data),
        "Classement Categorie": get_category_rank_label(site_data),
        "Categorie": clean_category_name(site_data.get("Category")),
        "Top 3 Pays": get_top_country_summary(site_data),
        "Top Mots-cles": get_top_keyword_summary(site_data),
        "Description": description,
    }


def split_batch_results(results: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    success_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    valid_results: dict[str, Any] = {}

    for domain, data in results.items():
        if is_valid_result(data):
            success_rows.append(build_domain_row(domain, data))
            valid_results[domain] = data
        else:
            error_rows.append(build_error_row(domain, data))

    return success_rows, error_rows, valid_results


def has_unique_visitors_values(dataframe: pd.DataFrame) -> bool:
    if "Visites uniques" not in dataframe.columns or dataframe.empty:
        return False
    series = dataframe["Visites uniques"]
    normalized = series.astype(str).str.strip().str.lower()
    missing_mask = series.isna() | normalized.isin({"", "none", "nan", "n/a"})
    return bool((~missing_mask).any())


def build_batch_context_summary(
    results: dict[str, Any],
    success_rows: list[dict[str, Any]],
    error_rows: list[dict[str, Any]],
    use_cache: bool,
    elapsed_time: float | None = None,
) -> dict[str, Any]:
    error_payloads = [payload for payload in results.values() if not is_valid_result(payload)]
    provider_blocked_payloads = [payload for payload in results.values() if is_provider_blocked_payload(payload)]
    rate_limited_count = sum(1 for payload in error_payloads if is_rate_limited_result(payload))
    global_rate_limit_detected = bool(provider_blocked_payloads) or any(is_global_rate_limit_result(payload) for payload in error_payloads) or (
        bool(error_payloads) and len(success_rows) == 0 and rate_limited_count == len(error_payloads)
    )
    snapshot_values = sorted(
        {
            row.get("Snapshot API")
            for row in success_rows
            if row.get("Snapshot API") and row.get("Snapshot API") != "N/A"
        }
    )
    period_values = sorted(
        {
            row.get("Periode donnee")
            for row in success_rows
            if row.get("Periode donnee") and row.get("Periode donnee") != "N/A"
        }
    )
    warning_message = None
    warning_level = None
    if global_rate_limit_detected:
        warning_level = "error"
        warning_message = "Blocage global Similarweb detecte pour cette session ou cette IP. Le domaine n'est probablement pas en cause."
    elif rate_limited_count > 0:
        warning_level = "warning"
        warning_message = f"Similarweb a limite {rate_limited_count} requete(s) sur ce lot. Reduisez la cadence ou utilisez des proxys."

    return {
        "total": len(results),
        "success": len(success_rows),
        "error": len(error_rows),
        "use_cache": use_cache,
        "elapsed_time": round(elapsed_time, 2) if elapsed_time is not None else None,
        "latest_snapshot": snapshot_values[-1] if snapshot_values else "N/A",
        "latest_period": period_values[-1] if period_values else "N/A",
        "rate_limited_count": rate_limited_count,
        "warning_level": warning_level,
        "warning_message": warning_message,
    }


def build_history_dataframe(history_entries: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entry in history_entries:
        payload = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        timestamp = entry.get("timestamp")
        collect_dt = None
        if timestamp:
            try:
                collect_dt = datetime.fromisoformat(timestamp)
            except ValueError:
                collect_dt = None

        rows.append(
            {
                "Date collecte": collect_dt,
                "Timestamp": timestamp,
                "Periode donnee": get_latest_data_period(payload),
                "Snapshot API": get_snapshot_label(payload),
                "Visites mensuelles": get_latest_monthly_visits(payload) or 0,
                "Classement global": get_global_rank(payload) or 0,
                "Taux de rebond (%)": round((parse_float_value((payload.get("Engagments") or {}).get("BounceRate")) or 0.0) * 100, 2),
                "Source serie": "Snapshots Similarweb sauvegardes localement",
            }
        )

    dataframe = pd.DataFrame(rows)
    if not dataframe.empty and "Date collecte" in dataframe.columns:
        dataframe = dataframe.sort_values("Date collecte")
    return dataframe


def build_period_analysis_row(domain: str, history_entries: list[dict[str, Any]], period_start: datetime, period_end: datetime) -> dict[str, Any]:
    visits_list: list[int] = []
    ranks_list: list[int] = []
    bounce_rates: list[float] = []
    pages_per_visit_list: list[float] = []
    duration_list: list[float] = []
    direct_traffic: list[float] = []
    organic_traffic: list[float] = []
    paid_traffic: list[float] = []
    social_traffic: list[float] = []
    email_traffic: list[float] = []
    snapshots: list[str] = []
    periods: list[str] = []

    for entry in history_entries:
        payload = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        visits = get_latest_monthly_visits(payload)
        if visits:
            visits_list.append(visits)

        rank = get_global_rank(payload)
        if rank:
            ranks_list.append(rank)

        snapshot_label = get_snapshot_label(payload)
        if snapshot_label != "N/A":
            snapshots.append(snapshot_label)

        data_period = get_latest_data_period(payload)
        if data_period != "N/A":
            periods.append(data_period)

        engagements = payload.get("Engagments") if isinstance(payload.get("Engagments"), dict) else {}
        traffic_sources = payload.get("TrafficSources") if isinstance(payload.get("TrafficSources"), dict) else {}

        bounce = parse_float_value(engagements.get("BounceRate"))
        if bounce is not None:
            bounce_rates.append(bounce * 100)

        pages = parse_float_value(engagements.get("PagePerVisit"))
        if pages is not None:
            pages_per_visit_list.append(pages)

        duration = parse_float_value(engagements.get("TimeOnSite"))
        if duration is not None:
            duration_list.append(duration / 60)

        direct = parse_float_value(traffic_sources.get("Direct"))
        if direct is not None:
            direct_traffic.append(direct * 100)

        organic = parse_float_value(traffic_sources.get("Search"))
        if organic is not None:
            organic_traffic.append(organic * 100)

        paid = (parse_float_value(traffic_sources.get("Paid")) or 0.0) + (
            parse_float_value(traffic_sources.get("Paid Referrals")) or 0.0
        )
        if paid:
            paid_traffic.append(paid * 100)

        social = parse_float_value(traffic_sources.get("Social"))
        if social is not None:
            social_traffic.append(social * 100)

        email = parse_float_value(traffic_sources.get("Mail"))
        if email is not None:
            email_traffic.append(email * 100)

    row = {
        "Domaine": domain,
        "Periode analysee": f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}",
        "Nb points de collecte": len(history_entries),
        "Source serie": "Historique local de snapshots",
        "Dernier snapshot API": snapshots[-1] if snapshots else "N/A",
        "Derniere periode donnee": periods[-1] if periods else "N/A",
        "Visites moyennes (M)": round((sum(visits_list) / len(visits_list)) / 1_000_000, 2) if visits_list else 0.0,
        "Visites min (M)": round(min(visits_list) / 1_000_000, 2) if visits_list else 0.0,
        "Visites max (M)": round(max(visits_list) / 1_000_000, 2) if visits_list else 0.0,
        "Evolution visites (%)": round(((visits_list[-1] - visits_list[0]) / visits_list[0] * 100), 2) if len(visits_list) >= 2 and visits_list[0] > 0 else 0.0,
        "Classement moyen": round(sum(ranks_list) / len(ranks_list)) if ranks_list else None,
        "Evolution classement": (ranks_list[-1] - ranks_list[0]) if len(ranks_list) >= 2 else None,
        "Taux rebond moyen (%)": round(sum(bounce_rates) / len(bounce_rates), 2) if bounce_rates else 0.0,
        "Pages/visite moyenne": round(sum(pages_per_visit_list) / len(pages_per_visit_list), 2) if pages_per_visit_list else 0.0,
        "Duree moyenne (min)": round(sum(duration_list) / len(duration_list), 2) if duration_list else 0.0,
        "Trafic direct moyen (%)": round(sum(direct_traffic) / len(direct_traffic), 2) if direct_traffic else 0.0,
        "Trafic organique moyen (%)": round(sum(organic_traffic) / len(organic_traffic), 2) if organic_traffic else 0.0,
        "Trafic payant moyen (%)": round(sum(paid_traffic) / len(paid_traffic), 2) if paid_traffic else 0.0,
        "Trafic social moyen (%)": round(sum(social_traffic) / len(social_traffic), 2) if social_traffic else 0.0,
        "Trafic email moyen (%)": round(sum(email_traffic) / len(email_traffic), 2) if email_traffic else 0.0,
    }
    return row


def format_int_display(value: Any) -> str:
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def format_decimal_display(value: Any, decimals: int = 2) -> str:
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    try:
        return f"{float(value):,.{decimals}f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def format_rank_display(value: Any) -> str:
    if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    try:
        return f"#{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)
