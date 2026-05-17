"""Compact NetworkX node-link Plotly diagram."""
from __future__ import annotations

import plotly.graph_objects as go

from core.graph import build_order_graph
from core.optimizer import RouteResult
from core.warehouse import Order
from data.warehouse_config import METHOD_COLORS, METHOD_LABELS, ZONE_COLORS


def graph_figure(order: Order, route: RouteResult) -> go.Figure:
    g = build_order_graph(order)
    node_x = [g.nodes[n]["pos"][0] for n in g.nodes]
    node_y = [g.nodes[n]["pos"][1] for n in g.nodes]
    node_color, node_text = [], []
    for n in g.nodes:
        if n == 0:
            node_color.append("#cccccc")
            node_text.append("DOCK")
        else:
            sku = order.skus[n - 1]
            node_color.append(ZONE_COLORS[sku.zone])
            node_text.append(f"{sku.brand}<br>{sku.name}")

    fig = go.Figure()
    rx, ry = [], []
    for a, b in zip(route.route[:-1], route.route[1:]):
        rx.extend([g.nodes[a]["pos"][0], g.nodes[b]["pos"][0], None])
        ry.extend([g.nodes[a]["pos"][1], g.nodes[b]["pos"][1], None])
    fig.add_trace(go.Scatter(
        x=rx, y=ry, mode="lines",
        line=dict(color=METHOD_COLORS[route.method], width=2),
        name=METHOD_LABELS[route.method], hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y, mode="markers",
        marker=dict(size=10, color=node_color, line=dict(color="white", width=1)),
        hovertext=node_text, hoverinfo="text", name="Nodes",
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0b0b", plot_bgcolor="#0b0b0b",
        height=420, margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(title="x (m)", gridcolor="#222"),
        yaxis=dict(title="y (m)", gridcolor="#222", scaleanchor="x", scaleratio=1),
    )
    return fig
