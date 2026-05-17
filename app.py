"""Picking Route Optimizer — V3.

Realistic 300x200 m warehouse with 4 thermal compartments (Frozen / Fresh /
Heavy / Ambient), real French SKU catalog, anti-cold doors with time
penalties, U-shape per-aisle picking, 4 algorithms, multi-operator wave
picking, cart capacity, deadlines, incidents, separate forklift system,
8 stretch wrappers, 12-tab UI.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from core.cart import needs_split, split_order_into_trips
from core.deadline import check_deadline, suggest_operators
from core.exporters import (
    export_excel_report,
    export_pdf_picking_list,
    export_route_csv,
)
from core.forklift import plan_forklift_routes
from core.history import (
    aggregate_pick_heatmap,
    cumulative_savings_eur,
    load_history,
    make_record,
    per_operator_summary,
    save_record,
    clear_history,
)
from core.incidents import IncidentScenario, apply_incidents
from core.metrics import (
    aisle_visit_sequence,
    annual_projection,
    attach_efficiency,
    compare_to_naive,
    compute_metrics,
    format_duration_hms,
    format_minutes,
    per_zone_distance,
    per_zone_sku_count,
    per_zone_time,
    step_by_step,
)
from core.optimizer import RouteResult, solve_all
from core.warehouse import Order, order_from_dataframe
from core.wave_picking import plan_wave
from core.wrappers import assign_pallets, make_pallets_from_order
from data.operators import PICKERS, picker_by_id
from data.sample_orders import PRESETS, random_order
from data.warehouse_config import (
    AISLES,
    METHOD_COLORS,
    METHOD_LABELS,
    PRIMARY_DOCK,
    WRAPPERS,
    WarehouseConfig,
    ZONES,
    ZONE_COLORS,
    ZONE_LABELS,
)
from visualization.animation import animated_route
from visualization.charts import (
    annual_savings_chart,
    cumulative_distance_chart,
    distance_bar_chart,
    side_by_side_routes,
    sku_count_per_zone_chart,
    time_per_zone_chart,
    wrapper_throughput_chart,
    wrapper_utilization_chart,
    zone_breakdown_chart,
    zone_donut_chart,
)
from visualization.heatmap import pick_heatmap
from visualization.map_view import build_map, build_minimap
from visualization.view_3d import warehouse_3d


# --------------------------------------------------------------------------- #
# Page + CSS
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="Picking Route Optimizer V3",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_css() -> None:
    css_path = Path(__file__).parent / "assets" / "style.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


_inject_css()


# Force the Folium / Leaflet container to dark (so no world background bleeds)
st.markdown(
    "<style>"
    ".leaflet-container { background: #0b0b0b !important; }"
    ".leaflet-control-attribution { display: none !important; }"
    "</style>",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Bootstrap
# --------------------------------------------------------------------------- #
def _bootstrap() -> None:
    if "order" not in st.session_state:
        st.session_state.order = random_order(
            n_skus=25, seed=42, deadline_minutes=45,
            order_id="ORD-AUTOSTART",
        )


_bootstrap()


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("## 📦 Picking Route Optimizer V3")
    st.caption("300x200 m · 4 thermal zones · 24 aisles · 1100+ SKU slots")

    st.markdown("### Order configuration")
    n_skus = st.slider("Number of SKUs", 5, 80, 25, step=1)
    seed = st.number_input("Random seed", value=42, step=1, format="%d")
    deadline_min = st.number_input("Deadline (minutes)", 5, 240, 45, 5)
    op_options = {f"{p.op_id} — {p.name} ({p.preferred_zone})": p.op_id for p in PICKERS}
    op_label = st.selectbox(
        "Picker", list(op_options.keys()),
        index=0,
    )
    op_id = op_options[op_label]

    if st.button("🎲 Generate random order", use_container_width=True, type="primary"):
        st.session_state.order = random_order(
            n_skus=n_skus, seed=int(seed),
            operator_id=op_id, deadline_minutes=int(deadline_min),
        )

    preset = st.selectbox("Preset orders", list(PRESETS.keys()), index=1)
    if st.button("📋 Load preset", use_container_width=True):
        st.session_state.order = PRESETS[preset]()

    upload = st.file_uploader("Upload CSV order", type=["csv"])
    if upload is not None:
        try:
            df = pd.read_csv(upload)
            st.session_state.order = order_from_dataframe(
                df, order_id="ORD-CSV",
                operator_id=op_id,
                operator_name=picker_by_id(op_id).name,
            )
            st.success(f"Loaded {len(df)} SKUs from CSV.")
        except Exception as exc:
            st.error(f"CSV load failed: {exc}")

    st.markdown("---")
    st.markdown("### Warehouse parameters")
    operator_speed = st.slider("Operator speed (m/s)", 0.8, 1.5, 1.2, 0.05)
    hourly_cost = st.number_input("Hourly cost (€)", 15.0, 30.0, 18.0, 0.5)
    solver_time_limit = st.slider("OR-Tools time limit (s)", 5, 30, 10, 1)
    cart_max_w = st.number_input("Cart max weight (kg)", 100.0, 500.0, 250.0, 10.0)
    cart_max_v = st.number_input("Cart max volume (m³)", 0.5, 3.0, 1.5, 0.1)

    st.markdown("---")
    st.markdown("### Wave picking")
    n_operators = st.slider("Operators in wave", 1, 8, 1, 1)

    st.markdown("---")
    st.markdown("### Forklifts")
    n_forklifts = st.slider("Forklifts on shift", 0, 4, 2, 1)

    st.markdown("---")
    st.markdown("### Incident simulation")
    sim_blocked = st.selectbox("Block aisle", ["(none)"] + list(AISLES))
    missing_options = ["(none)"] + [s.sku_id for s in st.session_state.order.skus]
    sim_missing = st.selectbox("Missing SKU", missing_options)
    wrapper_options = ["(none)"] + [w.label for w in WRAPPERS]
    sim_wrapper = st.selectbox("Wrapper out of service", wrapper_options)
    sim_forklift_down = st.checkbox("All forklifts unavailable", value=False)

    st.markdown("---")
    st.markdown("### Display")
    method_choice = st.radio(
        "Method on map",
        options=["constrained", "or_tools", "nearest_neighbor", "naive"],
        format_func=lambda m: METHOD_LABELS[m],
        index=0,
    )
    show_all_routes = st.checkbox("Overlay all routes on map", value=False)
    show_forklift_overlay = st.checkbox("Show forklift routes overlay", value=False)

    st.caption("Built with Streamlit, OR-Tools, NetworkX & Folium.")


# --------------------------------------------------------------------------- #
# Effective config + incidents
# --------------------------------------------------------------------------- #
config = WarehouseConfig(
    operator_speed_mps=float(operator_speed),
    hourly_cost_eur=float(hourly_cost),
    solver_time_limit_sec=int(solver_time_limit),
    cart_max_weight_kg=float(cart_max_w),
    cart_max_volume_m3=float(cart_max_v),
)

scenario = IncidentScenario(
    blocked_aisle=None if sim_blocked == "(none)" else sim_blocked,
    missing_sku_id=None if sim_missing == "(none)" else sim_missing,
    wrapper_down=None if sim_wrapper == "(none)" else sim_wrapper,
    forklift_unavailable=sim_forklift_down,
)
order_active, incident_effect = apply_incidents(st.session_state.order, scenario)


# --------------------------------------------------------------------------- #
# Solve (cached)
# --------------------------------------------------------------------------- #
def _signature(order: Order) -> tuple:
    return (
        order.order_id,
        tuple((s.sku_id, s.aisle, s.position, s.quantity) for s in order.skus),
    )


@st.cache_data(show_spinner=False)
def _solve(
    sig: tuple,
    or_time: int,
    speed: float,
    cost: float,
    cart_w: float,
    cart_v: float,
    fb_sig: tuple,
    _order: Order,
    _forbidden: list,
):
    cfg = WarehouseConfig(
        operator_speed_mps=speed, hourly_cost_eur=cost,
        solver_time_limit_sec=or_time,
        cart_max_weight_kg=cart_w, cart_max_volume_m3=cart_v,
    )
    results = solve_all(
        _order,
        or_tools_time_limit_sec=or_time,
        operator_speed_mps=speed,
        forbidden_node_pairs=_forbidden or None,
    )
    metrics = {m: compute_metrics(_order, r, cfg) for m, r in results.items()}
    attach_efficiency(metrics)
    return results, metrics, cfg


fb = incident_effect.forbidden_node_pairs
fb_sig = tuple(sorted(fb)) if fb else ()
with st.spinner("Solving with OR-Tools..."):
    results, metrics, _ = _solve(
        _signature(order_active),
        int(solver_time_limit),
        float(operator_speed),
        float(hourly_cost),
        float(cart_max_w),
        float(cart_max_v),
        fb_sig,
        order_active,
        fb,
    )


# Forklift plan
with st.spinner("Planning forklift replenishment..."):
    forklift_plan = plan_forklift_routes(
        order=order_active,
        seed=int(seed),
        n_forklifts=n_forklifts,
        unavailable=incident_effect.forklift_unavailable or n_forklifts == 0,
    )


# --------------------------------------------------------------------------- #
# Order banner
# --------------------------------------------------------------------------- #
order = order_active
zones = order.zones_covered
aisles = order.aisles_covered
zone_pills = " ".join(
    f'<span class="legend-pill" style="background:{ZONE_COLORS[z]}22;color:{ZONE_COLORS[z]}">'
    f'{z} · {ZONE_LABELS[z]}</span>'
    for z in zones
)

st.markdown(
    f"""
<div class="order-banner">
  <div class="order-line-1">📦 Order {order.order_id} · {order.size} SKUs · {len(zones)} zone(s) · {len(aisles)} aisle(s) · {order.total_weight_kg:.1f} kg · {order.total_volume_l:.1f} L</div>
  <div class="order-line-2">{order.created_at} · Picker {order.operator_id} ({order.operator_name}) · Aisles: {", ".join(aisles)}</div>
  <div style="margin-top:8px">{zone_pills}</div>
</div>
""",
    unsafe_allow_html=True,
)

if incident_effect.notes:
    for note in incident_effect.notes:
        st.warning(f"⚠️ {note}")


# --------------------------------------------------------------------------- #
# 4 metric cards
# --------------------------------------------------------------------------- #
def _delta(method: str) -> str:
    if method == "naive":
        return '<div class="delta baseline">baseline</div>'
    base = metrics["naive"].distance_m
    diff = metrics[method].distance_m - base
    pct = (diff / base * 100.0) if base else 0.0
    if pct < -5:
        return f'<div class="delta positive">🟢 {pct:+.1f}% vs naive</div>'
    if pct < 0:
        return f'<div class="delta neutral">🟡 {pct:+.1f}% vs naive</div>'
    return f'<div class="delta baseline">▫ {pct:+.1f}% vs naive</div>'


def _card(method: str) -> str:
    m = metrics[method]
    color = METHOD_COLORS[method]
    return f"""
<div class="metric-card" style="border-top:3px solid {color}">
  <div class="method-label" style="color:{color}">{METHOD_LABELS[method]}</div>
  <div class="big-value">{m.distance_m:,.0f} m</div>
  <div class="sub-value">{format_minutes(m.total_time_sec)} · €{m.cost_eur:.2f}</div>
  <div class="sub-value">{m.aisle_changes} aisle changes · {m.door_crossings} doors · score {m.efficiency_score}</div>
  {_delta(method)}
</div>
"""


cols = st.columns(4, gap="medium")
for col, method in zip(cols, ["naive", "nearest_neighbor", "or_tools", "constrained"]):
    with col:
        st.markdown(_card(method), unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Status row: deadline · cart · cold chain
# --------------------------------------------------------------------------- #
chosen_metrics = metrics[method_choice]
deadline_check = check_deadline(
    start_at=datetime.now(),
    total_time_sec=chosen_metrics.total_time_sec,
    deadline_minutes=order.deadline_minutes,
)

s1, s2, s3 = st.columns([1.4, 1, 1])
with s1:
    if deadline_check.has_deadline:
        if deadline_check.severity == "ok":
            st.success(
                f"⏱️ Deadline OK — finish {deadline_check.finish_at.strftime('%H:%M:%S')}, "
                f"deadline {deadline_check.deadline_at.strftime('%H:%M:%S')} "
                f"({deadline_check.slack_minutes:+.1f} min slack)"
            )
        elif deadline_check.severity == "tight":
            st.warning(
                f"⏱️ Deadline tight — only {deadline_check.slack_minutes:.1f} min slack."
            )
        else:
            need = suggest_operators(chosen_metrics.total_time_sec, order.deadline_minutes)
            st.error(
                f"⏱️ Deadline BREACH by {abs(deadline_check.slack_minutes):.1f} min — "
                f"recommend wave picking with **{need} operators**."
            )
    else:
        st.info("⏱️ No deadline configured.")

with s2:
    if needs_split(order, config):
        trips = split_order_into_trips(order, config)
        st.error(
            f"🛒 Cart over capacity — {order.total_weight_kg:.0f} kg / "
            f"{order.total_volume_l:.0f} L → split into **{len(trips)} trips**."
        )
    else:
        wp = order.total_weight_kg / config.cart_max_weight_kg * 100
        vp = order.total_volume_l / (config.cart_max_volume_m3 * 1000) * 100
        st.success(f"🛒 Cart fits — {wp:.0f}% kg / {vp:.0f}% volume.")

with s3:
    cold_sec = chosen_metrics.cold_chain_seconds
    if cold_sec == 0:
        st.info("❄️ No frozen items in this order.")
    elif cold_sec / 60.0 > 8:
        st.error(
            f"❄️ COLD CHAIN BREACH — frozen exposure {cold_sec/60:.1f} min "
            f"(limit 8 min). Use constrained method."
        )
    elif cold_sec / 60.0 > 5:
        st.warning(f"❄️ Cold chain tight — {cold_sec/60:.1f} min exposure.")
    else:
        st.success(f"❄️ Cold chain OK — {cold_sec/60:.1f} min exposure.")


# --------------------------------------------------------------------------- #
# 12 tabs
# --------------------------------------------------------------------------- #
tabs = st.tabs([
    "🏠 Overview",
    "🗺️ Warehouse Map",
    "📋 Step-by-step",
    "💶 Economic gains",
    "📊 Zone analysis",
    "📈 Route comparison",
    "🧊 3D view",
    "🎬 Animation",
    "🚜 Forklift system",
    "🎞 Filmeuses (wrappers)",
    "🔥 Heatmap",
    "📚 History",
])

(
    tab_over, tab_map, tab_step, tab_econ, tab_zone, tab_compare,
    tab_3d, tab_anim, tab_forklift, tab_film, tab_heat, tab_hist
) = tabs


# ------------------------- Tab 1: Overview ------------------------- #
with tab_over:
    st.markdown("### Order summary")
    odf = order.to_dataframe()
    st.dataframe(odf, use_container_width=True, hide_index=True, height=300)

    cA, cB = st.columns(2)
    with cA:
        st.plotly_chart(distance_bar_chart(metrics), use_container_width=True,
                        key="overview_distance_bar")
    with cB:
        st.plotly_chart(zone_donut_chart(order, results[method_choice]),
                        use_container_width=True, key="overview_zone_donut")

    st.markdown("##### Picking method explained")
    st.write(
        "The **constrained** algorithm enforces the mandatory pick order "
        "(heavy → ambient → fresh → frozen LAST), uses **U-shape** within each aisle "
        "(odd positions on the way down the left side, even positions on the way up "
        "the right side), and accounts for **anti-cold door delays** (8s for the fresh door, "
        "12s for the frozen door). It pays a small distance overhead vs pure OR-Tools "
        "but dramatically reduces frozen-item exposure."
    )


# ------------------------- Tab 2: Warehouse Map ------------------------- #
with tab_map:
    st.markdown("### 🗺️ Warehouse layout & picking route")
    map_col, side_col = st.columns([4, 1])
    with map_col:
        fmap = build_map(
            order, results,
            active_method=method_choice,
            show_all_routes=show_all_routes,
            show_forklift=show_forklift_overlay,
            forklift_routes=forklift_plan.forklift_routes,
            blocked_aisle=scenario.blocked_aisle,
            disabled_wrapper=scenario.wrapper_down,
        )
        st_folium(fmap, width=None, height=700, returned_objects=[])
    with side_col:
        st.markdown("**Mini-map**")
        mini = build_minimap(order, results[method_choice], METHOD_COLORS[method_choice])
        st_folium(mini, width=None, height=320, returned_objects=[])
        st.markdown("**Active method**")
        st.markdown(f"**{METHOD_LABELS[method_choice]}**")
        st.caption(f"Distance: {results[method_choice].distance_m:.0f} m")
        st.caption(f"Solver: {results[method_choice].solver_time_sec:.2f}s")
        st.caption(f"{results[method_choice].notes}")

        st.markdown("**Legend**")
        for code, zone in ZONES.items():
            st.markdown(
                f"<span class='legend-pill' "
                f"style='background:{ZONE_COLORS[code]}22;color:{ZONE_COLORS[code]}'>"
                f"{code} {zone.label}</span>",
                unsafe_allow_html=True,
            )


# ------------------------- Tab 3: Step-by-step ------------------------- #
with tab_step:
    st.markdown(f"#### Picking sequence — {METHOD_LABELS[method_choice]}")
    df_steps = step_by_step(order, results[method_choice], config)

    def _row_style(row):
        bg = ""
        if row["Door crossed"]:
            bg = "background-color: #5a1a1a; color: #fff;"
        elif row["Zone"] in ZONE_COLORS:
            bg = f"background-color: {ZONE_COLORS[row['Zone']]}22; color: #f4f4f4;"
        return [bg] * len(row)

    st.dataframe(
        df_steps.style.apply(_row_style, axis=1),
        use_container_width=True, hide_index=True, height=540,
    )


# ------------------------- Tab 4: Economic gains ------------------------- #
with tab_econ:
    proj = annual_projection(metrics, config)
    cA, cB = st.columns(2)
    with cA:
        st.plotly_chart(distance_bar_chart(metrics), use_container_width=True,
                        key="econ_distance_bar")
    with cB:
        st.plotly_chart(zone_donut_chart(order, results[method_choice]),
                        use_container_width=True, key="econ_zone_donut")

    st.markdown("#### Annual projection (60 orders/day × 250 days)")
    st.dataframe(
        pd.DataFrame({
            "Method": [METHOD_LABELS[m] for m in proj],
            "Annual distance (km)": [round(proj[m]["annual_distance_km"], 0) for m in proj],
            "Annual hours": [round(proj[m]["annual_hours"], 0) for m in proj],
            "Annual cost (€)": [round(proj[m]["annual_cost_eur"], 0) for m in proj],
            "Annual savings vs naive (€)": [
                round(proj[m]["annual_savings_vs_naive_eur"], 0) for m in proj
            ],
        }),
        use_container_width=True, hide_index=True,
    )
    st.plotly_chart(annual_savings_chart(proj), use_container_width=True,
                    key="econ_annual_savings")

    or_save = proj["or_tools"]["annual_savings_vs_naive_eur"]
    cn_save = proj["constrained"]["annual_savings_vs_naive_eur"]
    st.success(
        f"💰 Annual savings vs naive — pure OR-Tools: **€{or_save:,.0f}/year**, "
        f"constrained (cold chain compliant): **€{cn_save:,.0f}/year**."
    )


# ------------------------- Tab 5: Zone analysis ------------------------- #
with tab_zone:
    cA, cB = st.columns(2)
    with cA:
        st.plotly_chart(sku_count_per_zone_chart(order), use_container_width=True,
                        key="zone_sku_count")
        st.plotly_chart(time_per_zone_chart(order, results[method_choice], config),
                        use_container_width=True, key="zone_time_per_zone")
    with cB:
        st.plotly_chart(zone_breakdown_chart(order, results), use_container_width=True,
                        key="zone_breakdown")

    st.markdown(f"#### Aisle visit sequence — {METHOD_LABELS[method_choice]}")
    seq = aisle_visit_sequence(order, results[method_choice])
    st.markdown(
        " → ".join(
            f"<span class='legend-pill' style='background:#222;color:#eee'>{a}</span>"
            for a in seq
        ),
        unsafe_allow_html=True,
    )

    counts = per_zone_sku_count(order)
    distances = per_zone_distance(order, results[method_choice])
    times = per_zone_time(order, results[method_choice], config)
    st.dataframe(
        pd.DataFrame({
            "Zone": [f"{z} · {ZONES[z].label}" for z in ZONES],
            "# SKUs": [counts[z] for z in ZONES],
            "Distance (m)": [round(distances[z], 1) for z in ZONES],
            "Time (min)": [round(times[z] / 60.0, 2) for z in ZONES],
            "Temperature": [f"{ZONES[z].temperature_c:.0f}°C" for z in ZONES],
        }),
        use_container_width=True, hide_index=True,
    )


# ------------------------- Tab 6: Route comparison ------------------------- #
with tab_compare:
    st.plotly_chart(cumulative_distance_chart(order, results), use_container_width=True,
                    key="compare_cumulative")
    st.markdown("#### Side-by-side comparison (4 algorithms)")
    st.plotly_chart(
        side_by_side_routes(order, results, ["naive", "nearest_neighbor", "or_tools", "constrained"]),
        use_container_width=True, key="compare_side_by_side",
    )

    comp = compare_to_naive(metrics)
    st.dataframe(
        pd.DataFrame({
            "Method": [METHOD_LABELS[m] for m in metrics],
            "Distance (m)": [round(metrics[m].distance_m, 1) for m in metrics],
            "Time (min)": [round(metrics[m].total_time_sec / 60.0, 2) for m in metrics],
            "Cost (€)": [round(metrics[m].cost_eur, 3) for m in metrics],
            "Aisle changes": [metrics[m].aisle_changes for m in metrics],
            "Cross-aisle": [metrics[m].cross_aisle_uses for m in metrics],
            "Door crossings": [metrics[m].door_crossings for m in metrics],
            "Door delay (s)": [round(metrics[m].door_delay_sec, 1) for m in metrics],
            "Cold-chain (s)": [round(metrics[m].cold_chain_seconds, 1) for m in metrics],
            "Saved m": [round(comp[m]["distance_saved_m"], 1) for m in metrics],
            "Saved %": [round(comp[m]["distance_saved_pct"], 1) for m in metrics],
            "Solver (s)": [round(results[m].solver_time_sec, 3) for m in metrics],
            "Score": [metrics[m].efficiency_score for m in metrics],
        }),
        use_container_width=True, hide_index=True,
    )


# ------------------------- Tab 7: 3D view ------------------------- #
with tab_3d:
    st.markdown("#### 3D warehouse — picker (z=0) + forklift (rack height)")
    st.plotly_chart(
        warehouse_3d(order, results, method_choice,
                     forklift_routes=forklift_plan.forklift_routes
                     if not forklift_plan.unavailable else None),
        use_container_width=True, key="view_3d_warehouse",
    )
    st.caption(
        "Picker route is at floor level (z = 0). Forklift routes (dashed orange) "
        "operate at mid-rack height (~3.5 m) and are independent from picker traffic."
    )


# ------------------------- Tab 8: Animation ------------------------- #
with tab_anim:
    st.markdown("#### Operator walking the picking route")
    st.caption("Press ▶ Play. The cart weight & volume update live as items are picked.")
    st.plotly_chart(
        animated_route(order, results[method_choice]),
        use_container_width=True, key="anim_walker",
    )


# ------------------------- Tab 9: Forklift system ------------------------- #
with tab_forklift:
    st.markdown("### 🚜 Forklift replenishment system")
    if forklift_plan.unavailable:
        st.error("All forklifts are unavailable — replenishment is paused.")
    else:
        kp1, kp2, kp3, kp4 = st.columns(4)
        kp1.metric("Forklifts on shift", n_forklifts)
        kp2.metric("Pending replenishments", forklift_plan.pending_tasks)
        kp3.metric("Total distance", f"{forklift_plan.total_distance_m:.0f} m")
        kp4.metric("Total time", format_duration_hms(forklift_plan.total_time_sec))

        st.markdown("#### Dispatch queue")
        for fr in forklift_plan.forklift_routes:
            with st.expander(
                f"🚜 {fr.forklift_id} — {fr.driver_name} · "
                f"{len(fr.tasks)} tasks · "
                f"{fr.total_distance_m:.0f} m · "
                f"{format_duration_hms(fr.total_time_sec)}",
                expanded=False,
            ):
                if not fr.tasks:
                    st.info("No tasks assigned.")
                else:
                    st.dataframe(
                        pd.DataFrame([{
                            "Aisle": t.aisle,
                            "Position": t.position,
                            "Zone": t.zone,
                            "Units to move": t.units_to_move,
                            "Priority": t.priority,
                            "Estimated time (s)": round(t.estimated_seconds, 1),
                        } for t in fr.tasks]),
                        use_container_width=True, hide_index=True,
                    )
        st.caption(
            "Forklifts run a separate OR-Tools TSP from the heavy-zone dock. "
            "Priority order: FROZEN → FRESH → AMBIENT → HEAVY (cold chain first)."
        )


# ------------------------- Tab 10: Filmeuses ------------------------- #
with tab_film:
    st.markdown("### 🎞 Stretch wrapper (filmeuse) system")
    pallets = make_pallets_from_order(order, n_per_zone_factor=3)
    plan = assign_pallets(pallets, disabled_wrapper=scenario.wrapper_down)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Wrappers online", len([s for s in plan.states if not s.out_of_service]))
    k2.metric("Pallets in queue", sum(len(s.queue) for s in plan.states))
    k3.metric("Avg wait", format_duration_hms(plan.avg_wait_sec))
    k4.metric("Bottleneck", plan.bottleneck or "—")

    if plan.out_of_service:
        st.warning("Out of service: " + ", ".join(plan.out_of_service))

    cA, cB = st.columns(2)
    with cA:
        st.plotly_chart(wrapper_utilization_chart(plan.states), use_container_width=True,
                        key="film_utilization")
    with cB:
        st.plotly_chart(wrapper_throughput_chart(plan.states), use_container_width=True,
                        key="film_throughput")

    st.dataframe(
        pd.DataFrame([{
            "Wrapper": s.wrapper.label,
            "Zone": s.wrapper.zone_code,
            "Status": "OUT OF SERVICE" if s.out_of_service else "ONLINE",
            "Pallets processed": s.pallets_processed,
            "Queue (now)": len(s.queue),
            "Utilization (%)": round(s.utilization_pct, 1),
            "Capacity (pal/h)": s.wrapper.capacity_pallets_per_hour,
        } for s in plan.states]),
        use_container_width=True, hide_index=True,
    )


# ------------------------- Tab 11: Wave picking inside Heatmap? Reorganize ------------------------- #
# Wave picking goes inline below the route comparison — move below.

# ------------------------- Tab 11: Heatmap ------------------------- #
with tab_heat:
    st.markdown("#### Pick-frequency heatmap (cumulative across history)")
    history = load_history()
    visits = aggregate_pick_heatmap(history)
    st.plotly_chart(pick_heatmap(visits), use_container_width=True,
                    key="heatmap_pick_frequency")
    if visits:
        top = sorted(visits.items(), key=lambda kv: -kv[1])[:10]
        st.markdown("##### Top 10 most-picked slots")
        st.dataframe(
            pd.DataFrame(top, columns=["Slot", "Picks"]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No history yet — save an order from the History tab.")


# ------------------------- Tab 12: History ------------------------- #
with tab_hist:
    history = load_history()

    cA, cB, cC = st.columns(3)
    cA.metric("Orders saved", len(history))
    cB.metric("Cumulative savings", f"€{cumulative_savings_eur(history):,.2f}")
    adoption = (
        f"{(sum(1 for r in history if r.chosen_method in ('or_tools','constrained')) / max(len(history),1) * 100):.0f}%"
        if history else "—"
    )
    cC.metric("Optimizer adoption", adoption)

    bA, bB = st.columns(2)
    if bA.button("💾 Save current order to history", use_container_width=True):
        rec = make_record(order, metrics, method_choice)
        save_record(rec)
        st.success(f"Saved {rec.order_id}.")
        history = load_history()
    if bB.button("🗑️ Clear history", use_container_width=True):
        clear_history()
        history = []
        st.success("History cleared.")

    if history:
        st.markdown("#### Per-operator performance")
        st.dataframe(
            pd.DataFrame(per_operator_summary(history)),
            use_container_width=True, hide_index=True,
        )
        st.markdown("#### Recent orders")
        st.dataframe(
            pd.DataFrame([{
                "When": r.timestamp.replace("T", " "),
                "Order": r.order_id,
                "Operator": f"{r.operator_id} {r.operator_name}",
                "SKUs": r.n_skus,
                "Method": METHOD_LABELS.get(r.chosen_method, r.chosen_method),
                "Distance (m)": r.chosen_distance_m,
                "Time (min)": r.chosen_time_min,
                "Cold (s)": r.cold_chain_seconds,
                "Doors": r.door_crossings,
                "Saved (€)": r.savings_vs_naive_eur,
                "Saved (%)": r.savings_vs_naive_pct,
            } for r in history]),
            use_container_width=True, hide_index=True, height=420,
        )
    else:
        st.info("No history yet — save your first order above.")


# --------------------------------------------------------------------------- #
# Wave picking section (always visible at bottom of page)
# --------------------------------------------------------------------------- #
st.markdown("---")
st.markdown(f"### 👷 Wave picking — {n_operators} operator(s)")
wave = plan_wave(order, n_operators=n_operators, config=config)
if wave.operators:
    k1, k2, k3 = st.columns(3)
    k1.metric("Total walking distance (sum)", f"{wave.total_distance_m:.0f} m")
    k2.metric("Parallel time (slowest op.)", format_duration_hms(wave.parallel_time_sec))
    k3.metric("Operators used", str(len(wave.operators)))
    st.dataframe(
        pd.DataFrame([{
            "Operator": f"{o.operator_id} {o.operator_name}",
            "Zones": ", ".join(o.zones),
            "# SKUs": o.sub_order.size,
            "Distance (m)": round(o.metrics.distance_m, 1),
            "Time (min)": round(o.metrics.total_time_sec / 60.0, 2),
            "Cold (s)": round(o.metrics.cold_chain_seconds, 1),
            "Cost (€)": round(o.metrics.cost_eur, 2),
        } for o in wave.operators]),
        use_container_width=True, hide_index=True,
    )
else:
    st.info("No SKUs to dispatch.")


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #
st.markdown("### 📤 Export")
e1, e2, e3 = st.columns(3)
with e1:
    st.download_button(
        "⬇️ CSV (route)",
        data=export_route_csv(order, results[method_choice], config),
        file_name=f"{order.order_id}_{method_choice}_route.csv",
        mime="text/csv",
        use_container_width=True,
    )
with e2:
    st.download_button(
        "⬇️ Excel (full report)",
        data=export_excel_report(order, results, metrics, config),
        file_name=f"{order.order_id}_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
with e3:
    st.download_button(
        "⬇️ PDF picking list (with QR)",
        data=export_pdf_picking_list(order, results[method_choice], config),
        file_name=f"{order.order_id}_picking_list.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

st.caption(
    f"Solved {order.size} SKUs · OR-Tools time limit {solver_time_limit}s · "
    f"Constrained method enforces heavy→ambient→fresh→FROZEN ordering, "
    f"U-shape per aisle, and door-time penalties."
)
