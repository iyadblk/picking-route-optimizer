"""CSV / Excel / PDF exporters."""
from __future__ import annotations

import io
from typing import Dict

import pandas as pd

from core.metrics import (
    RouteMetrics,
    annual_projection,
    compare_to_naive,
    step_by_step,
)
from core.optimizer import RouteResult
from core.warehouse import Order
from data.warehouse_config import METHOD_LABELS, WarehouseConfig


def export_route_csv(order: Order, result: RouteResult, config: WarehouseConfig) -> bytes:
    return step_by_step(order, result, config).to_csv(index=False).encode("utf-8")


def export_excel_report(
    order: Order,
    results: Dict[str, RouteResult],
    metrics: Dict[str, RouteMetrics],
    config: WarehouseConfig,
) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        order.to_dataframe().to_excel(writer, index=False, sheet_name="Order")

        comp = compare_to_naive(metrics)
        pd.DataFrame({
            "Method": [METHOD_LABELS[m] for m in metrics],
            "Distance (m)": [round(metrics[m].distance_m, 1) for m in metrics],
            "Total time (min)": [round(metrics[m].total_time_sec / 60.0, 2) for m in metrics],
            "Cost (€)": [round(metrics[m].cost_eur, 3) for m in metrics],
            "Aisle changes": [metrics[m].aisle_changes for m in metrics],
            "Cross-aisle uses": [metrics[m].cross_aisle_uses for m in metrics],
            "Door crossings": [metrics[m].door_crossings for m in metrics],
            "Door delay (s)": [round(metrics[m].door_delay_sec, 1) for m in metrics],
            "Cold-chain (s)": [round(metrics[m].cold_chain_seconds, 1) for m in metrics],
            "Saved vs naive (m)": [round(comp[m]["distance_saved_m"], 1) for m in metrics],
            "Saved vs naive (%)": [round(comp[m]["distance_saved_pct"], 1) for m in metrics],
            "Efficiency": [metrics[m].efficiency_score for m in metrics],
        }).to_excel(writer, index=False, sheet_name="Comparison")

        proj = annual_projection(metrics, config)
        pd.DataFrame({
            "Method": [METHOD_LABELS[m] for m in proj],
            "Annual distance (km)": [round(proj[m]["annual_distance_km"], 0) for m in proj],
            "Annual hours": [round(proj[m]["annual_hours"], 0) for m in proj],
            "Annual cost (€)": [round(proj[m]["annual_cost_eur"], 0) for m in proj],
            "Annual savings vs naive (€)": [round(proj[m]["annual_savings_vs_naive_eur"], 0) for m in proj],
        }).to_excel(writer, index=False, sheet_name="Annual projection")

        for name, res in results.items():
            sheet = f"Steps - {METHOD_LABELS[name]}"[:31]
            step_by_step(order, res, config).to_excel(writer, index=False, sheet_name=sheet)

    return buf.getvalue()


def export_pdf_picking_list(
    order: Order,
    result: RouteResult,
    config: WarehouseConfig,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )
    import qrcode

    df = step_by_step(order, result, config)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], textColor=colors.HexColor("#222"))
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.grey, fontSize=10)

    elements = [
        Paragraph(f"Picking List — {order.order_id}", title_style),
        Paragraph(
            f"Operator: {order.operator_id} ({order.operator_name}) &nbsp;|&nbsp; "
            f"{order.created_at} &nbsp;|&nbsp; "
            f"Method: {METHOD_LABELS[result.method]} &nbsp;|&nbsp; "
            f"Distance: {result.distance_m:.0f} m &nbsp;|&nbsp; SKUs: {order.size}",
            sub_style,
        ),
        Spacer(1, 5 * mm),
    ]

    header = ["#", "Brand", "Product", "Zone", "Aisle", "Pos", "Side", "Cart kg", "QR"]
    data = [header]
    qr_buffers = []

    for _, row in df.iterrows():
        if row["Product"] == "DOCK":
            qr_cell = ""
        else:
            qr = qrcode.QRCode(box_size=2, border=1)
            qr.add_data(f"{row['Brand']}|{row['Product']}|{row['Aisle']}|{row['Position']}")
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            b = io.BytesIO()
            img.save(b, format="PNG")
            b.seek(0)
            qr_cell = Image(b, width=12 * mm, height=12 * mm)
            qr_buffers.append(b)

        data.append([
            str(row["Step"]),
            str(row["Brand"]),
            str(row["Product"])[:32],
            str(row["Zone"]),
            str(row["Aisle"]),
            str(row["Position"]),
            str(row["Side"]),
            str(row["Cart kg"]),
            qr_cell,
        ])

    table = Table(
        data,
        colWidths=[8 * mm, 26 * mm, 56 * mm, 18 * mm,
                   12 * mm, 10 * mm, 10 * mm, 16 * mm, 14 * mm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f1f1f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.whitesmoke, colors.HexColor("#f1f1f1")]),
    ]))
    elements.append(table)
    doc.build(elements)
    return buf.getvalue()
