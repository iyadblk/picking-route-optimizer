"""Plotly charts for analytics tabs + side-by-side route comparison."""
from __future__ import annotations

from typing import Dict, List

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.metrics import (
    RouteMetrics,
    cumulative_distance_curve,
    per_zone_distance,
    per_zone_sku_count,
    per_zone_time,
)
from core.optimizer import RouteResult
from core.warehouse import Order
from data.warehouse_config import (
    AISLE_X,
    AISLES,
    DOORS,
    METHOD_COLORS,
    METHOD_LABELS,
    PRIMARY_DOCK,
    WAREHOUSE_HEIGHT,
    WAREHOUSE_WIDTH,
    WarehouseConfig,
    ZONE_COLORS,
    ZONE_OF_AISLE,
    ZONES,
)


_DARK = dict(
    template="plotly_dark",
    paper_bgcolor="#0b0b0b",
    plot_bgcolor="#0b0b0b",
)

_METHOD_ORDER = ["naive", "nearest_neighbor", "or_tools", "constrained"]


def distance_bar_chart(metrics: Dict[str, RouteMetrics]) -> go.Figure:
    methods = [m for m in _METHOD_ORDER if m in metrics]
    fig = go.Figure(go.Bar(
        x=[METHOD_LABELS[m] for m in methods],
        y=[metrics[m].distance_m for m in methods],
        marker=dict(color=[METHOD_COLORS[m] for m in methods]),
        text=[f"{metrics[m].distance_m:.0f} m" for m in methods],
        textposition="outside",
    ))
    fig.update_layout(
        title="Total walking distance per method",
        height=380, margin=dict(l=10, r=10, t=50, b=10),
        yaxis=dict(title="Distance (m)", gridcolor="#222"),
        xaxis=dict(gridcolor="#222"),
        **_DARK,
    )
    return fig


def zone_donut_chart(order: Order, result: RouteResult) -> go.Figure:
    distances = per_zone_distance(order, result)
    keys = list(ZONES.keys()) + ["DOCK"]
    labels = [ZONES[k].label if k in ZONES else "Dock travel" for k in keys]
    values = [distances[k] for k in keys]
    colors = [ZONE_COLORS.get(k, "#888") for k in keys]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.55,
        marker=dict(colors=colors, line=dict(color="#0b0b0b", width=2)),
        textinfo="percent",
        hovertemplate="%{label}<br>%{value:.1f} m<extra></extra>",
    ))
    fig.update_layout(
        title=f"Distance by zone — {METHOD_LABELS[result.method]}",
        height=380, margin=dict(l=10, r=10, t=50, b=10),
        **_DARK,
    )
    return fig


def cumulative_distance_chart(order: Order, results: Dict[str, RouteResult]) -> go.Figure:
    fig = go.Figure()
    for method in _METHOD_ORDER:
        if method not in results:
            continue
        r = results[method]
        cum = cumulative_distance_curve(order, r)
        fig.add_trace(go.Scatter(
            x=list(range(len(cum))), y=cum,
            mode="lines+markers",
            name=METHOD_LABELS[method],
            line=dict(color=METHOD_COLORS[method], width=3),
            marker=dict(size=4),
        ))
    fig.update_layout(
        title="Cumulative distance by step",
        xaxis=dict(title="Step #", gridcolor="#222"),
        yaxis=dict(title="Cumulative distance (m)", gridcolor="#222"),
        height=420, margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=-0.18),
        **_DARK,
    )
    return fig


def zone_breakdown_chart(order: Order, results: Dict[str, RouteResult]) -> go.Figure:
    methods = [m for m in _METHOD_ORDER if m in results]
    keys = list(ZONES.keys()) + ["DOCK"]
    fig = go.Figure()
    for k in keys:
        label = ZONES[k].label if k in ZONES else "Dock"
        fig.add_trace(go.Bar(
            name=label,
            x=[METHOD_LABELS[m] for m in methods],
            y=[per_zone_distance(order, results[m])[k] for m in methods],
            marker_color=ZONE_COLORS.get(k, "#888"),
        ))
    fig.update_layout(
        barmode="stack",
        title="Distance by zone, per method",
        yaxis=dict(title="Distance (m)", gridcolor="#222"),
        xaxis=dict(gridcolor="#222"),
        height=400, margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=-0.2),
        **_DARK,
    )
    return fig


def sku_count_per_zone_chart(order: Order) -> go.Figure:
    counts = per_zone_sku_count(order)
    keys = list(ZONES.keys())
    fig = go.Figure(go.Bar(
        x=[ZONES[k].label for k in keys],
        y=[counts[k] for k in keys],
        marker=dict(color=[ZONE_COLORS[k] for k in keys]),
        text=[counts[k] for k in keys], textposition="outside",
    ))
    fig.update_layout(
        title="SKUs per zone in this order",
        yaxis=dict(title="# SKUs", gridcolor="#222"),
        xaxis=dict(gridcolor="#222"),
        height=320, margin=dict(l=10, r=10, t=50, b=10),
        **_DARK,
    )
    return fig


def time_per_zone_chart(
    order: Order, result: RouteResult, config: WarehouseConfig
) -> go.Figure:
    times = per_zone_time(order, result, config)
    keys = list(ZONES.keys())
    fig = go.Figure(go.Bar(
        x=[ZONES[k].label for k in keys],
        y=[times[k] / 60.0 for k in keys],
        marker=dict(color=[ZONE_COLORS[k] for k in keys]),
        text=[f"{times[k]/60.0:.1f} min" for k in keys],
        textposition="outside",
    ))
    fig.update_layout(
        title=f"Time per zone (incl. doors) — {METHOD_LABELS[result.method]}",
        yaxis=dict(title="Time (min)", gridcolor="#222"),
        xaxis=dict(gridcolor="#222"),
        height=340, margin=dict(l=10, r=10, t=50, b=10),
        **_DARK,
    )
    return fig


def annual_savings_chart(annual_proj: Dict[str, Dict[str, float]]) -> go.Figure:
    methods = [m for m in _METHOD_ORDER if m in annual_proj]
    fig = go.Figure(go.Bar(
        x=[METHOD_LABELS[m] for m in methods],
        y=[annual_proj[m]["annual_cost_eur"] for m in methods],
        marker=dict(color=[METHOD_COLORS[m] for m in methods]),
        text=[f"€{annual_proj[m]['annual_cost_eur']:,.0f}" for m in methods],
        textposition="outside",
    ))
    fig.update_layout(
        title="Projected annual labor cost (60 orders/day x 250 days)",
        yaxis=dict(title="Annual cost (€)", gridcolor="#222"),
        xaxis=dict(gridcolor="#222"),
        height=380, margin=dict(l=10, r=10, t=50, b=10),
        **_DARK,
    )
    return fig


def side_by_side_routes(
    order: Order,
    results: Dict[str, RouteResult],
    methods: List[str],
) -> go.Figure:
    n = len(methods)
    fig = make_subplots(
        rows=1, cols=n,
        subplot_titles=[
            f"{METHOD_LABELS[m]}<br><sub>{results[m].distance_m:.0f} m</sub>"
            for m in methods
        ],
        horizontal_spacing=0.03,
    )
    for col, method in enumerate(methods, start=1):
        # Zone tints
        for code, zone in ZONES.items():
            c = ZONE_COLORS[code]
            fig.add_shape(
                type="rect",
                x0=zone.x_min, x1=zone.x_max, y0=zone.y_min, y1=zone.y_max,
                line=dict(color=c, width=0.5), fillcolor=c, opacity=0.10,
                row=1, col=col, layer="below",
            )
        # Aisles
        for a in AISLES:
            zone = ZONES[ZONE_OF_AISLE[a]]
            ax = AISLE_X[a]
            fig.add_shape(
                type="rect",
                x0=ax - 1.4, x1=ax + 1.4,
                y0=zone.y_min + 2, y1=zone.y_max - 2,
                line=dict(color="#3a3a3a", width=0.4), fillcolor="#1c1c1c",
                row=1, col=col, layer="below",
            )
        # Doors
        for door in DOORS:
            fig.add_shape(
                type="line", x0=door.x_min, x1=door.x_max,
                y0=door.y, y1=door.y,
                line=dict(color="#FF0033", width=3),
                row=1, col=col,
            )

        # SKUs
        fig.add_trace(go.Scatter(
            x=[s.coord[0] for s in order.skus],
            y=[s.coord[1] for s in order.skus],
            mode="markers",
            marker=dict(size=4, color=[ZONE_COLORS[s.zone] for s in order.skus],
                        line=dict(color="white", width=0.4)),
            showlegend=False, hoverinfo="skip",
        ), row=1, col=col)

        # Route
        r = results[method]
        rx = []; ry = []
        for idx in r.route:
            if idx == 0:
                rx.append(PRIMARY_DOCK.x); ry.append(PRIMARY_DOCK.y)
            else:
                rx.append(order.skus[idx - 1].coord[0])
                ry.append(order.skus[idx - 1].coord[1])
        fig.add_trace(go.Scatter(
            x=rx, y=ry, mode="lines",
            line=dict(color=METHOD_COLORS[method], width=2),
            showlegend=False, hoverinfo="skip",
        ), row=1, col=col)

        # Dock
        fig.add_trace(go.Scatter(
            x=[PRIMARY_DOCK.x], y=[PRIMARY_DOCK.y],
            mode="markers",
            marker=dict(size=8, color="#00C896", symbol="diamond"),
            showlegend=False, hoverinfo="skip",
        ), row=1, col=col)

        fig.update_xaxes(range=[-5, WAREHOUSE_WIDTH + 5], visible=False,
                         row=1, col=col)
        fig.update_yaxes(range=[-5, WAREHOUSE_HEIGHT + 5], visible=False,
                         row=1, col=col, scaleanchor=f"x{col}", scaleratio=0.7)

    fig.update_layout(
        height=400, margin=dict(l=5, r=5, t=50, b=5),
        **_DARK,
    )
    return fig


# --------------------------------------------------------------------------- #
# Wrapper-system gauges
# --------------------------------------------------------------------------- #
def wrapper_utilization_chart(states) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=[s.wrapper.label for s in states],
        y=[s.utilization_pct for s in states],
        marker=dict(color=[
            "#FF4B4B" if s.utilization_pct > 85 else
            ("#FFB347" if s.utilization_pct > 60 else "#00C896")
            for s in states
        ]),
        text=[f"{s.utilization_pct:.0f}%" for s in states],
        textposition="outside",
    ))
    fig.add_hline(y=85, line_dash="dash", line_color="#FF4B4B",
                  annotation_text="Saturation 85%", annotation_position="top right")
    fig.update_layout(
        title="Stretch wrapper utilization",
        yaxis=dict(title="Utilization (%)", range=[0, 110], gridcolor="#222"),
        xaxis=dict(gridcolor="#222", tickangle=-30),
        height=400, margin=dict(l=10, r=10, t=50, b=80),
        **_DARK,
    )
    return fig


def wrapper_throughput_chart(states) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=[s.wrapper.label for s in states],
        y=[s.pallets_processed for s in states],
        marker=dict(color="#BF7FFF"),
        text=[s.pallets_processed for s in states], textposition="outside",
    ))
    fig.update_layout(
        title="Pallets processed per wrapper",
        yaxis=dict(title="# pallets", gridcolor="#222"),
        xaxis=dict(gridcolor="#222", tickangle=-30),
        height=340, margin=dict(l=10, r=10, t=50, b=80),
        **_DARK,
    )
    return fig
