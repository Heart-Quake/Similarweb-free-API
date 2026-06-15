from __future__ import annotations

import io
import json
import os
import tempfile
from datetime import datetime
from urllib.request import urlopen

import pandas as pd
import streamlit as st

from ui_builders import (
    format_decimal_display,
    format_int_display,
    get_large_screenshot_url,
    get_site_name,
    get_snapshot_label,
    get_top_keyword_rows,
)
from ui_charts import (
    create_engagement_figure,
    create_top_countries_figure,
    create_traffic_sources_figure,
    create_visits_trend_figure,
)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

try:
    import kaleido  # noqa: F401

    HAS_KALEIDO = True
except ImportError:
    HAS_KALEIDO = False


def _figure_to_image(figure, output_path: str) -> str | None:
    if figure is None or not HAS_KALEIDO:
        return None
    try:
        figure.write_image(output_path, width=900, height=520, scale=1)
        return output_path if os.path.exists(output_path) else None
    except Exception:
        return None


def _download_remote_image(url: str | None, output_path: str) -> str | None:
    if not url:
        return None
    try:
        with urlopen(url, timeout=15) as response:
            content = response.read()
        with open(output_path, "wb") as file_handle:
            file_handle.write(content)
        return output_path if os.path.exists(output_path) else None
    except Exception:
        return None


def generate_pdf_report(results, success_rows, error_rows, output_path=None, progress_callback=None):
    if not HAS_REPORTLAB:
        return None

    temp_dir = tempfile.mkdtemp(prefix="similarweb_pdf_")
    output_path = output_path or tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name

    try:
        document = SimpleDocTemplate(output_path, pagesize=A4)
        story = []
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontSize=22,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=18,
        )
        section_style = ParagraphStyle(
            "SectionTitle",
            parent=styles["Heading2"],
            fontSize=15,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=12,
            spaceAfter=10,
        )

        story.append(Paragraph("Rapport Similarweb", title_style))
        story.append(Paragraph(f"Genere le {datetime.now().strftime('%d/%m/%Y a %H:%M')}", styles["BodyText"]))
        story.append(Spacer(1, 0.2 * inch))

        summary_table = Table(
            [
                ["Domaines", len(results)],
                ["Succes", len(success_rows)],
                ["Erreurs", len(error_rows)],
            ],
            colWidths=[2.5 * inch, 1.2 * inch],
        )
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 0.25 * inch))

        if success_rows:
            dataframe = pd.DataFrame(success_rows)
            export_columns = [
                column
                for column in [
                    "Domaine",
                    "Snapshot API",
                    "Periode donnee",
                    "Visites (M)",
                    "Taux de rebond (%)",
                    "Trafic organique (%)",
                    "Classement global",
                ]
                if column in dataframe.columns
            ]
            table_data = [export_columns]
            for _, row in dataframe[export_columns].iterrows():
                formatted_row = []
                for column in export_columns:
                    value = row[column]
                    if column == "Visites (M)":
                        formatted_row.append(format_decimal_display(value))
                    elif column == "Classement global":
                        formatted_row.append(format_int_display(value))
                    else:
                        formatted_row.append(str(value) if value is not None else "N/A")
                table_data.append(formatted_row)

            recap_table = Table(table_data, repeatRows=1)
            recap_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(Paragraph("Recapitulatif", section_style))
            story.append(recap_table)
            story.append(PageBreak())

        valid_results = {domain: data for domain, data in results.items() if isinstance(data, dict) and "error" not in data}
        total_sites = len(valid_results)

        for index, (domain, site_data) in enumerate(sorted(valid_results.items()), 1):
            site_name = get_site_name(site_data, domain)
            if progress_callback:
                progress_callback(index, total_sites, f"Generation du PDF pour {domain}")

            story.append(Paragraph(site_name, section_style))
            story.append(Paragraph(f"Snapshot API: {get_snapshot_label(site_data)}", styles["BodyText"]))
            story.append(Spacer(1, 0.1 * inch))

            metrics_table = Table(
                [
                    ["Visites mensuelles", format_int_display((site_data.get("EstimatedMonthlyVisits") or {}).get(sorted((site_data.get("EstimatedMonthlyVisits") or {}).keys())[-1]) if isinstance(site_data.get("EstimatedMonthlyVisits"), dict) and site_data.get("EstimatedMonthlyVisits") else None)],
                    ["Categorie", str(site_data.get("Category") or "N/A")],
                    ["Description", str(site_data.get("Description") or "N/A")[:140]],
                ],
                colWidths=[1.8 * inch, 5.2 * inch],
            )
            metrics_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(metrics_table)
            story.append(Spacer(1, 0.15 * inch))

            screenshot_path = _download_remote_image(
                get_large_screenshot_url(site_data),
                os.path.join(temp_dir, f"screenshot_{index}.png"),
            )
            if screenshot_path:
                story.append(Image(screenshot_path, width=6.8 * inch, height=3.8 * inch))
                story.append(Spacer(1, 0.12 * inch))

            for figure, name in [
                (create_visits_trend_figure(site_data), "visits"),
                (create_traffic_sources_figure(site_data), "traffic"),
                (create_top_countries_figure(site_data), "countries"),
                (create_engagement_figure(site_data), "engagement"),
            ]:
                image_path = _figure_to_image(figure, os.path.join(temp_dir, f"{name}_{index}.png"))
                if image_path:
                    story.append(Image(image_path, width=6.8 * inch, height=3.6 * inch))
                    story.append(Spacer(1, 0.12 * inch))

            keyword_rows = get_top_keyword_rows(site_data, limit=10)
            if keyword_rows:
                keyword_table_data = [["Mot-cle", "Volume", "CPC", "Valeur estimee"]]
                for row in keyword_rows:
                    keyword_table_data.append(
                        [
                            row.get("Mot-cle") or "N/A",
                            format_int_display(row.get("Volume")),
                            format_decimal_display(row.get("CPC")),
                            format_int_display(row.get("Valeur estimee")),
                        ]
                    )
                keyword_table = Table(keyword_table_data, repeatRows=1)
                keyword_table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
                            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ]
                    )
                )
                story.append(Paragraph("Top mots-cles", styles["Heading3"]))
                story.append(keyword_table)

            if index < total_sites:
                story.append(PageBreak())

        document.build(story)
        return output_path
    finally:
        for root, _, files in os.walk(temp_dir):
            for file_name in files:
                try:
                    os.unlink(os.path.join(root, file_name))
                except OSError:
                    pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass


def render_export_panel(df_results: pd.DataFrame, results: dict, success_rows: list[dict], error_rows: list[dict], key_prefix: str) -> None:
    st.subheader("Exports")
    col_csv, col_json, col_pdf = st.columns(3)

    with col_csv:
        csv_data = df_results.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="Telecharger CSV",
            data=csv_data,
            file_name=f"similarweb_{key_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key=f"csv_{key_prefix}",
        )

    with col_json:
        json_data = json.dumps(results, indent=2, ensure_ascii=False)
        st.download_button(
            label="Telecharger JSON",
            data=json_data,
            file_name=f"similarweb_{key_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            key=f"json_{key_prefix}",
        )

    with col_pdf:
        if not HAS_REPORTLAB:
            st.info("reportlab non installe")
            return

        pdf_state_key = f"pdf_bytes_{key_prefix}"
        if st.button("Generer PDF", use_container_width=True, key=f"pdf_generate_{key_prefix}"):
            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(current, total, message):
                progress = current / total if total else 0
                progress_bar.progress(progress)
                status_text.info(f"{message} ({current}/{total})")

            try:
                pdf_path = generate_pdf_report(results, success_rows, error_rows, progress_callback=update_progress)
                with open(pdf_path, "rb") as file_handle:
                    st.session_state[pdf_state_key] = file_handle.read()
                os.unlink(pdf_path)
                progress_bar.progress(1.0)
                status_text.success("PDF pret")
            except Exception as error:
                status_text.error(f"Erreur PDF: {error}")

        pdf_bytes = st.session_state.get(pdf_state_key)
        if pdf_bytes:
            st.download_button(
                label="Telecharger PDF",
                data=pdf_bytes,
                file_name=f"similarweb_{key_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                key=f"pdf_download_{key_prefix}",
            )
