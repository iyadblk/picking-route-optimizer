"""3D Plotly view: warehouse footprint flat + forklift route at rack heights."""
from __future__ import annotations

from typing import Dict, List

import plotly.graph_objects as go

from core.optimizer import RouteResult
from core.warehouse import Order
from data.warehouse_config import (
    AISLE_X,
    AISLES,
    DOCKS,
    FORKLIFT_RACK_LEVELS,
    FORKLIFT_RACK_LEVEL_HEIGHT_M,
    METHOD_COLORS,
    METHOD_LABELS,
    PRIMARY_DOCK,
    WAREHOUSE_HEIGHT,
    WAREHOUSE_WIDTH,
    ZONE_COLORS,
    ZONE_OF_AISLE,
    ZONES,
)


def warehouse_3d(
    order: Order,
    results: Dict[str, RouteResult],
    active_method: str,
    forklift_routes: List = None,
) -> go.Figure:
    fig = go.Figure()

    # Floor
    fig.add_trace(go.Mesh3d(
        x=[0, WAREHOUSE_WIDTH, WAREHOUSE_WIDTH, 0],
        y=[0, 0, WAREHOUSE_HEIGHT, WAREHOUSE_HEIGHT],
        z=[0, 0, 0, 0],
        i=[0, 0], j=[1, 2], k=[2, 3],
        color="#1c1c1c", opacity=0.5,
        showscale=False, hoverinfo="skip", name="Floor",
    ))

    # Zone footprints
    for code, zone in ZONES.items():
        c = ZONE_COLORS[code]
        fig.add_trace(go.Mesh3d(
            x=[zone.x_min, zone.x_max, zone.x_max, zone.x_min],
            y=[zone.y_min, zone.y_min, zone.y_max, zone.y_max],
            z=[0.05, 0.05, 0.05, 0.05],
            i=[0, 0], j=[1, 2], k=[2, 3],
            color=c, opacity=0.20,
            showscale=False, hoverinfo="skip",
            name=code, showlegend=False,
        ))

    # Aisle racks (visible up to forklift rack height)
    rack_h = FORKLIFT_RACK_LEVELS * FORKLIFT_RACK_LEVEL_HEIGHT_M
    for aisle in AISLES:
        zone = ZONES[ZONE_OF_AISLE[aisle]]
        ax = AISLE_X[aisle]
        c = ZONE_COLORS[ZONE_OF_AISLE[aisle]]
        xs = [ax - 1.0, ax + 1.0, ax + 1.0, ax - 1.0,
              ax - 1.0, ax + 1.0, ax + 1.0, ax - 1.0]
        ys = [zone.y_min + 2, zone.y_min + 2, zone.y_max - 2, zone.y_max - 2,
              zone.y_min + 2, zone.y_min + 2, zone.y_max - 2, zone.y_max - 2]
        zs = [0, 0, 0, 0, rack_h, rack_h, rack_h, rack_h]
        fig.add_trace(go.Mesh3d(
            x=xs, y=ys, z=zs,
            i=[0, 0, 0, 1, 4, 4, 4, 5],
            j=[1, 3, 4, 2, 5, 7, 6, 6],
            k=[2, 4, 7, 3, 6, 4, 7, 7],
            color=c, opacity=0.08,
            showscale=False, hoverinfo="skip", showlegend=False,
        ))

    # Dock
    fig.add_trace(go.Scatter3d(
        x=[PRIMARY_DOCK.x], y=[PRIMARY_DOCK.y], z=[0.2],
        mode="markers+text",
        marker=dict(size=8, color="#00C896", symbol="diamond"),
        text=[PRIMARY_DOCK.label], textposition="top center",
        name="Dock",
    ))

    # SKUs at z=0
    fig.add_trace(go.Scatter3d(
        x=[s.coord[0] for s in order.skus],
        y=[s.coord[1] for s in order.skus],
        z=[0.4 for _ in order.skus],
        mode="markers",
        marker=dict(
            size=5,
            color=[ZONE_COLORS[s.zone] for s in order.skus],
            line=dict(color="white", width=1),
        ),
        hovertext=[f"{s.brand} - {s.name}<br>{s.aisle}{s.position:02d}"
                   for s in order.skus],
        hoverinfo="text",
        name="SKUs (picker level)",
    ))

    # Picker route (z=0)
    result = results[active_method]
    rx = []; ry = []
    for idx in result.route:
        if idx == 0:
            rx.append(PRIMARY_DOCK.x); ry.append(PRIMARY_DOCK.y)
        else:
            sku = order.skus[idx - 1]
            rx.append(sku.coord[0]); ry.append(sku.coord[1])
    fig.add_trace(go.Scatter3d(
        x=rx, y=ry, z=[0.4] * len(rx),
        mode="lines",
        line=dict(color=METHOD_COLORS[active_method], width=4),
        name=f"Picker — {METHOD_LABELS[active_method]}",
    ))

    # Forklift route at rack mid-height
    if forklift_routes:
        for fr in forklift_routes:
            if not fr.route_points or len(fr.route_points) < 2:
                continue
            fx = [p[0] for p in fr.route_points]
            fy = [p[1] for p in fr.route_points]
            fz = [rack_h * 0.6] * len(fx)
            fig.add_trace(go.Scatter3d(
                x=fx, y=fy, z=fz,
                mode="lines+markers",
                line=dict(color=METHOD_COLORS["forklift"], width=4, dash="dash"),
                marker=dict(size=4, color=METHOD_COLORS["forklift"]),
                name=f"Forklift {fr.forklift_id}",
            ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0b0b",
        scene=dict(
            xaxis=dict(title="x (m)", backgroundcolor="#0b0b0b", gridcolor="#222",
                       range=[0, WAREHOUSE_WIDTH]),
            yaxis=dict(title="y (m)", backgroundcolor="#0b0b0b", gridcolor="#222",
                       range=[0, WAREHOUSE_HEIGHT]),
            zaxis=dict(title="height (m)", backgroundcolor="#0b0b0b", gridcolor="#222",
                       range=[0, rack_h + 1]),
            aspectmode="manual",
            aspectratio=dict(x=2.5, y=1.7, z=0.5),
        ),
        height=600,
        margin=dict(l=0, r=0, t=20, b=0),
        legend=dict(orientation="h", y=-0.05),
    )
    return fig
