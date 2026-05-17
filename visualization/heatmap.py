"""Pick-frequency heatmap aggregated over history."""
from __future__ import annotations

from typing import Dict

import numpy as np
import plotly.graph_objects as go

from data.warehouse_config import (
    AISLE_X,
    AISLES,
    WAREHOUSE_HEIGHT,
    WAREHOUSE_WIDTH,
    ZONES,
    ZONE_OF_AISLE,
    position_xy,
)


def pick_heatmap(visits: Dict[str, int]) -> go.Figure:
    # Build a per-(aisle, position) scatter where size encodes frequency
    xs, ys, sizes, texts = [], [], [], []
    for aisle in AISLES:
        zone = ZONES[ZONE_OF_AISLE[aisle]]
        for p in range(1, zone.positions_per_aisle + 1):
            key = f"{aisle}-{p:02d}"
            v = visits.get(key, 0)
            if v == 0:
                continue
            x, y = position_xy(aisle, p)
            xs.append(x)
            ys.append(y)
            sizes.append(8 + v * 4)
            texts.append(f"{key} - {v} picks")

    fig = go.Figure()

    # Backdrop: zone tints
    for code, zone in ZONES.items():
        from data.warehouse_config import ZONE_COLORS
        c = ZONE_COLORS[code]
        fig.add_shape(
            type="rect",
            x0=zone.x_min, x1=zone.x_max, y0=zone.y_min, y1=zone.y_max,
            line=dict(color=c, width=1), fillcolor=c, opacity=0.10, layer="below",
        )

    if xs:
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers",
            marker=dict(
                size=sizes,
                color=sizes,
                colorscale="Hot",
                showscale=True,
                colorbar=dict(title="Picks"),
                line=dict(color="white", width=0.5),
            ),
            text=texts, hoverinfo="text",
            name="Pick frequency",
        ))
    else:
        fig.add_annotation(
            x=WAREHOUSE_WIDTH / 2, y=WAREHOUSE_HEIGHT / 2,
            text="No picks recorded yet", showarrow=False,
            font=dict(color="#9aa0a6", size=16),
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b0b0b",
        plot_bgcolor="#0b0b0b",
        title="Pick frequency heatmap (cumulative across history)",
        height=560,
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis=dict(title="x (m)", range=[-5, WAREHOUSE_WIDTH + 5], gridcolor="#222"),
        yaxis=dict(title="y (m)", range=[-5, WAREHOUSE_HEIGHT + 5], gridcolor="#222",
                   scaleanchor="x", scaleratio=1),
    )
    return fig
