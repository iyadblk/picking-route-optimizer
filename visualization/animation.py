"""Plotly animation: walker moving along the picking route, cart filling up."""
from __future__ import annotations

from typing import List, Tuple

import plotly.graph_objects as go

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
    ZONE_COLORS,
    ZONE_OF_AISLE,
    ZONES,
)


def _interp(p, q, steps):
    return [(p[0] + (q[0] - p[0]) * (s / steps),
             p[1] + (q[1] - p[1]) * (s / steps))
            for s in range(1, steps + 1)]


def animated_route(
    order: Order,
    result: RouteResult,
    steps_per_leg: int = 8,
) -> go.Figure:
    coords = [(PRIMARY_DOCK.x, PRIMARY_DOCK.y)]
    coords.extend(order.skus[i - 1].coord for i in result.route[1:-1])
    coords.append((PRIMARY_DOCK.x, PRIMARY_DOCK.y))

    sku_lookup = {i: order.skus[i - 1] for i in range(1, len(order.skus) + 1)}

    # Frames
    walker_x: List[float] = []
    walker_y: List[float] = []
    cart_kg: List[float] = []
    cart_l: List[float] = []
    sku_label: List[str] = []
    cur_kg, cur_l = 0.0, 0.0

    for (a, b), node_idx in zip(zip(coords[:-1], coords[1:]), result.route[1:]):
        for x, y in _interp(a, b, steps_per_leg):
            walker_x.append(x)
            walker_y.append(y)
            cart_kg.append(cur_kg)
            cart_l.append(cur_l)
            if node_idx == 0:
                sku_label.append("Returning to dock")
            else:
                s = sku_lookup[node_idx]
                sku_label.append(f"Heading to {s.brand} - {s.name}")
        if node_idx != 0:
            s = sku_lookup[node_idx]
            cur_kg += s.total_weight_kg
            cur_l += s.total_volume_l
            walker_x.append(s.coord[0])
            walker_y.append(s.coord[1])
            cart_kg.append(cur_kg)
            cart_l.append(cur_l)
            sku_label.append(f"PICKED {s.brand} - {s.name}")

    fig = go.Figure()

    # Zones background
    for code, zone in ZONES.items():
        c = ZONE_COLORS[code]
        fig.add_shape(
            type="rect",
            x0=zone.x_min, x1=zone.x_max, y0=zone.y_min, y1=zone.y_max,
            line=dict(color=c, width=1), fillcolor=c, opacity=0.10, layer="below",
        )

    # Aisles
    for a in AISLES:
        zone = ZONES[ZONE_OF_AISLE[a]]
        ax = AISLE_X[a]
        fig.add_shape(
            type="rect", x0=ax - 1.6, x1=ax + 1.6,
            y0=zone.y_min + 2, y1=zone.y_max - 2,
            line=dict(color="#3a3a3a", width=1), fillcolor="#1c1c1c", layer="below",
        )

    # Doors
    for door in DOORS:
        fig.add_shape(
            type="line", x0=door.x_min, x1=door.x_max, y0=door.y, y1=door.y,
            line=dict(color="#FF0033", width=4), layer="above",
        )

    # Static route
    rx = [c[0] for c in coords]
    ry = [c[1] for c in coords]
    color = METHOD_COLORS[result.method]
    fig.add_trace(go.Scatter(
        x=rx, y=ry,
        mode="lines",
        line=dict(color=color, width=2, dash="dot"),
        name=METHOD_LABELS[result.method],
        hoverinfo="skip",
    ))

    # SKUs
    fig.add_trace(go.Scatter(
        x=[s.coord[0] for s in order.skus],
        y=[s.coord[1] for s in order.skus],
        mode="markers",
        marker=dict(size=8, color=[ZONE_COLORS[s.zone] for s in order.skus],
                    line=dict(color="white", width=1)),
        text=[f"{s.brand} {s.name}" for s in order.skus],
        hoverinfo="text",
        name="SKUs",
    ))

    # Dock
    fig.add_trace(go.Scatter(
        x=[PRIMARY_DOCK.x], y=[PRIMARY_DOCK.y],
        mode="markers+text",
        marker=dict(size=14, color="#00C896", symbol="diamond"),
        text=[PRIMARY_DOCK.label], textposition="top center",
        name="Dock",
    ))

    # Walker (animated trace, last)
    fig.add_trace(go.Scatter(
        x=[walker_x[0]], y=[walker_y[0]],
        mode="markers",
        marker=dict(size=20, color="#FFFFFF", symbol="circle",
                    line=dict(color=color, width=3)),
        name="Operator",
    ))

    frames = [
        go.Frame(
            data=[
                go.Scatter(x=rx, y=ry),
                go.Scatter(
                    x=[s.coord[0] for s in order.skus],
                    y=[s.coord[1] for s in order.skus],
                ),
                go.Scatter(x=[PRIMARY_DOCK.x], y=[PRIMARY_DOCK.y]),
                go.Scatter(x=[walker_x[k]], y=[walker_y[k]]),
            ],
            name=str(k),
            layout=go.Layout(
                title=f"{sku_label[k]} — Cart: {cart_kg[k]:.1f} kg / {cart_l[k]:.1f} L"
            ),
        )
        for k in range(len(walker_x))
    ]
    fig.frames = frames

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0b0b",
        plot_bgcolor="#0b0b0b",
        height=620,
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis=dict(title="x (m)", range=[-5, WAREHOUSE_WIDTH + 5], gridcolor="#222"),
        yaxis=dict(title="y (m)", range=[-5, WAREHOUSE_HEIGHT + 5], gridcolor="#222",
                   scaleanchor="x", scaleratio=1),
        title=f"Cart: 0 kg / 0 L",
        updatemenus=[dict(
            type="buttons",
            showactive=False,
            x=0.02, y=1.07,
            buttons=[
                dict(label="▶ Play", method="animate",
                     args=[None, {"frame": {"duration": 50, "redraw": True},
                                  "fromcurrent": True, "transition": {"duration": 0}}]),
                dict(label="⏸ Pause", method="animate",
                     args=[[None], {"frame": {"duration": 0}, "mode": "immediate",
                                    "transition": {"duration": 0}}]),
            ],
        )],
    )
    return fig
