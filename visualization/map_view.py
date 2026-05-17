"""Folium map of the V3 warehouse — warehouse rectangle only, no world map.

We use CRS=Simple with `tiles=None`, then paint the warehouse manually.
The Leaflet container background is forced to dark via injected CSS in
`app.py` so the area outside the warehouse is dark, never showing a world.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import folium
from folium.features import DivIcon

from core.optimizer import RouteResult
from core.warehouse import Order
from data.warehouse_config import (
    AISLE_X,
    AISLE_HALF_WIDTH,
    AISLES,
    CROSS_AISLES,
    DOCKS,
    DOORS,
    METHOD_COLORS,
    METHOD_LABELS,
    PRIMARY_DOCK,
    WAREHOUSE_HEIGHT,
    WAREHOUSE_WIDTH,
    WRAPPERS,
    ZONES,
    ZONE_COLORS,
    ZONE_LABELS,
    ZONE_OF_AISLE,
    position_xy,
)


def _ll(x: float, y: float) -> Tuple[float, float]:
    """Cartesian (x meters east, y meters north) -> Folium (lat, lon).

    With CRS=Simple, lat = vertical axis, lon = horizontal axis.
    """
    return (y, x)


# --------------------------------------------------------------------------- #
# Map construction
# --------------------------------------------------------------------------- #
def _new_map() -> folium.Map:
    """Empty Leaflet canvas confined to the warehouse footprint."""
    sw = _ll(0, 0)
    ne = _ll(WAREHOUSE_WIDTH, WAREHOUSE_HEIGHT)
    fmap = folium.Map(
        location=_ll(WAREHOUSE_WIDTH / 2, WAREHOUSE_HEIGHT / 2),
        crs="Simple",
        zoom_start=1,
        min_zoom=-1,
        max_zoom=5,
        tiles=None,
        zoom_control=True,
        control_scale=False,
        max_bounds=True,
    )
    # Background warehouse rectangle
    folium.Rectangle(
        bounds=[sw, ne],
        color="#444",
        weight=2,
        fill=True,
        fill_color="#0f0f0f",
        fill_opacity=1.0,
    ).add_to(fmap)
    return fmap


def _draw_zones(fmap: folium.Map) -> None:
    for code, zone in ZONES.items():
        color = ZONE_COLORS[code]
        folium.Rectangle(
            bounds=[_ll(zone.x_min, zone.y_min), _ll(zone.x_max, zone.y_max)],
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.10,
            tooltip=f"{code} — {ZONE_LABELS[code]}",
        ).add_to(fmap)
        folium.Marker(
            _ll((zone.x_min + zone.x_max) / 2,
                (zone.y_min + zone.y_max) / 2 + (zone.y_max - zone.y_min) / 2 - 4),
            icon=DivIcon(
                icon_size=(160, 18), icon_anchor=(80, 9),
                html=(
                    f"<div style='color:{color};font-family:monospace;"
                    f"font-size:11px;font-weight:700;text-align:center;"
                    f"text-shadow:0 0 4px black'>{code} — {ZONE_LABELS[code]}</div>"
                ),
            ),
        ).add_to(fmap)


def _draw_aisles(fmap: folium.Map, blocked_aisle: Optional[str]) -> None:
    for aisle in AISLES:
        zone = ZONES[ZONE_OF_AISLE[aisle]]
        ax = AISLE_X[aisle]
        is_blocked = (aisle == blocked_aisle)
        # Aisle corridor (visual)
        folium.Rectangle(
            bounds=[
                _ll(ax - AISLE_HALF_WIDTH - 0.4, zone.y_min + 2.0),
                _ll(ax + AISLE_HALF_WIDTH + 0.4, zone.y_max - 2.0),
            ],
            color="#FF4B4B" if is_blocked else "#3a3a3a",
            weight=2 if is_blocked else 1,
            fill=True,
            fill_color="#5a1a1a" if is_blocked else "#1c1c1c",
            fill_opacity=0.85,
            tooltip=f"Aisle {aisle}" + (" (BLOCKED)" if is_blocked else ""),
        ).add_to(fmap)
        # Aisle label at the top of the aisle
        folium.Marker(
            _ll(ax, zone.y_max + 1.2),
            icon=DivIcon(
                icon_size=(40, 14), icon_anchor=(20, 7),
                html=(
                    f"<div style='color:#ddd;font-family:monospace;"
                    f"font-size:9px;font-weight:600;text-align:center'>{aisle}</div>"
                ),
            ),
        ).add_to(fmap)


def _draw_cross_aisles(fmap: folium.Map) -> None:
    for ca in CROSS_AISLES:
        folium.PolyLine(
            locations=[_ll(ca.x_min, ca.y), _ll(ca.x_max, ca.y)],
            color="#666666",
            weight=4,
            opacity=0.45,
            dash_array="2,4",
            tooltip=f"Cross-aisle {ca.label}",
        ).add_to(fmap)


def _draw_doors(fmap: folium.Map) -> None:
    for door in DOORS:
        folium.PolyLine(
            locations=[_ll(door.x_min, door.y), _ll(door.x_max, door.y)],
            color=door.color,
            weight=8,
            opacity=0.95,
            tooltip=f"{door.label} (+{door.delay_seconds}s per pass)",
        ).add_to(fmap)
        folium.Marker(
            _ll((door.x_min + door.x_max) / 2, door.y),
            icon=DivIcon(
                icon_size=(60, 12), icon_anchor=(30, 6),
                html=(
                    f"<div style='color:#ff6677;font-size:9px;font-weight:700;"
                    f"text-align:center;text-shadow:0 0 3px black'>"
                    f"❄ {door.label}</div>"
                ),
            ),
        ).add_to(fmap)


def _draw_docks(fmap: folium.Map) -> None:
    for d in DOCKS:
        is_primary = d.label == PRIMARY_DOCK.label
        color = "#00C896" if is_primary else "#cccccc"
        folium.CircleMarker(
            location=_ll(d.x, d.y),
            radius=10 if is_primary else 7,
            color="#000000",
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=1.0,
            popup=f"{d.label} ({d.kind})",
            tooltip=d.label,
        ).add_to(fmap)
        folium.Marker(
            _ll(d.x, d.y),
            icon=DivIcon(
                icon_size=(60, 12), icon_anchor=(30, -10),
                html=(
                    f"<div style='color:{color};font-size:10px;font-weight:700;"
                    f"text-align:center;text-shadow:0 0 3px black'>{d.label}</div>"
                ),
            ),
        ).add_to(fmap)


def _draw_wrappers(fmap: folium.Map, disabled_wrapper: Optional[str] = None) -> None:
    for w in WRAPPERS:
        disabled = (w.label == disabled_wrapper)
        folium.RegularPolygonMarker(
            location=_ll(w.x, w.y),
            number_of_sides=4,
            radius=7,
            rotation=45,
            color="#888888" if disabled else "#FFFFFF",
            weight=2,
            fill=True,
            fill_color="#FF4B4B" if disabled else "#BF7FFF",
            fill_opacity=0.9,
            popup=f"{w.label}{' (OUT OF SERVICE)' if disabled else ''}<br>"
                  f"{w.capacity_pallets_per_hour} pallets/h",
            tooltip=w.label,
        ).add_to(fmap)


def _draw_skus(fmap: folium.Map, order: Order, active_route: List[int]) -> None:
    passage_order: Dict[int, int] = {}
    step = 0
    for node_idx in active_route:
        if node_idx == 0:
            continue
        step += 1
        passage_order[node_idx] = step

    for i, sku in enumerate(order.skus, start=1):
        color = ZONE_COLORS[sku.zone]
        step_num = passage_order.get(i, "-")
        popup_html = (
            f"<b>{sku.brand} — {sku.name}</b><br>"
            f"SKU: <code>{sku.sku_id}</code><br>"
            f"Zone: {ZONE_LABELS[sku.zone]}<br>"
            f"Aisle {sku.aisle}, position {sku.position} ({'LEFT' if sku.side == 'L' else 'RIGHT'} side)<br>"
            f"{sku.quantity} unit(s) · {sku.total_weight_kg:.1f} kg · {sku.total_volume_l:.1f} L<br>"
            f"Fragile: {sku.fragile} · Priority: {sku.priority}<br>"
            f"<b>Pick sequence: #{step_num}</b>"
        )
        folium.CircleMarker(
            location=_ll(*sku.coord),
            radius=6 if sku.priority != "urgent" else 8,
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.92,
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=f"#{step_num} {sku.brand} {sku.name}",
        ).add_to(fmap)
        folium.Marker(
            _ll(*sku.coord),
            icon=DivIcon(
                icon_size=(20, 12), icon_anchor=(10, 6),
                html=(
                    f"<div style='color:white;font-size:8px;font-weight:700;"
                    f"text-align:center;text-shadow:0 0 3px black'>{step_num}</div>"
                ),
            ),
        ).add_to(fmap)


def _draw_route(
    fmap: folium.Map,
    order: Order,
    result: RouteResult,
    color: str,
    label: str,
    dashed: bool,
    weight: int = 4,
) -> None:
    coords: List[Tuple[float, float]] = []
    for idx in result.route:
        if idx == 0:
            coords.append(_ll(PRIMARY_DOCK.x, PRIMARY_DOCK.y))
        else:
            coords.append(_ll(*order.skus[idx - 1].coord))

    line_kwargs = dict(
        locations=coords,
        color=color,
        weight=weight if not dashed else max(2, weight - 1),
        opacity=0.92 if not dashed else 0.55,
        tooltip=f"{label}: {result.distance_m:.0f} m",
    )
    if dashed:
        line_kwargs["dash_array"] = "6,6"
    folium.PolyLine(**line_kwargs).add_to(fmap)

    # Direction arrows mid-leg
    for (a_lat, a_lon), (b_lat, b_lon) in zip(coords[:-1], coords[1:]):
        ml, mn = (a_lat + b_lat) / 2.0, (a_lon + b_lon) / 2.0
        ang = math.degrees(math.atan2(b_lon - a_lon, b_lat - a_lat))
        folium.Marker(
            (ml, mn),
            icon=DivIcon(
                icon_size=(12, 12), icon_anchor=(6, 6),
                html=(
                    f"<div style='transform: rotate({ang}deg);"
                    f"color:{color};font-size:11px;font-weight:900;"
                    f"line-height:12px'>&#9654;</div>"
                ),
            ),
        ).add_to(fmap)


# --------------------------------------------------------------------------- #
# Public builders
# --------------------------------------------------------------------------- #
def build_map(
    order: Order,
    routes: Dict[str, RouteResult],
    active_method: str,
    show_all_routes: bool = False,
    show_forklift: bool = False,
    forklift_routes: Optional[List] = None,
    blocked_aisle: Optional[str] = None,
    disabled_wrapper: Optional[str] = None,
) -> folium.Map:
    fmap = _new_map()
    _draw_zones(fmap)
    _draw_cross_aisles(fmap)
    _draw_aisles(fmap, blocked_aisle)
    _draw_doors(fmap)
    _draw_wrappers(fmap, disabled_wrapper)
    _draw_docks(fmap)
    _draw_skus(fmap, order, routes[active_method].route)

    # Routes
    if show_all_routes:
        for method, result in routes.items():
            _draw_route(fmap, order, result, METHOD_COLORS[method],
                        METHOD_LABELS[method], dashed=(method != active_method))
    else:
        _draw_route(fmap, order, routes[active_method],
                    METHOD_COLORS[active_method],
                    METHOD_LABELS[active_method], dashed=False)

    # Forklift routes overlay
    if show_forklift and forklift_routes:
        for fr in forklift_routes:
            if not fr.route_points or len(fr.route_points) < 2:
                continue
            coords = [_ll(x, y) for x, y in fr.route_points]
            folium.PolyLine(
                locations=coords,
                color=METHOD_COLORS["forklift"],
                weight=3,
                opacity=0.85,
                dash_array="3,5",
                tooltip=f"Forklift {fr.forklift_id} ({fr.driver_name}): {fr.total_distance_m:.0f} m",
            ).add_to(fmap)

    fmap.fit_bounds([_ll(0, 0), _ll(WAREHOUSE_WIDTH, WAREHOUSE_HEIGHT)])
    return fmap


def build_minimap(order: Order, route: RouteResult, color: str) -> folium.Map:
    fmap = _new_map()
    _draw_zones(fmap)
    coords: List[Tuple[float, float]] = []
    for idx in route.route:
        if idx == 0:
            coords.append(_ll(PRIMARY_DOCK.x, PRIMARY_DOCK.y))
        else:
            coords.append(_ll(*order.skus[idx - 1].coord))
    folium.PolyLine(coords, color=color, weight=2.5, opacity=0.95).add_to(fmap)
    fmap.fit_bounds([_ll(0, 0), _ll(WAREHOUSE_WIDTH, WAREHOUSE_HEIGHT)])
    return fmap
