# dashboard.py
# ──────────────────────────────────────────────────────────────
# Dashboard Streamlit — Operación UBER 2025 / 2026
# Usa business_rules.py para cargar y transformar datos.
# ──────────────────────────────────────────────────────────────
import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from business_rules import (
    load_ingresos,
    load_egresos,
    add_yearweek,
    yearweek_label,
)

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Dashboard Uber 2025-2026",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════
# CUSTOM THEME / CSS
# ═══════════════════════════════════════════════════════════════
st.markdown("""
<style>
    /* KPI cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    div[data-testid="stMetric"] label {
        color: #a8b8d8 !important;
        font-size: 0.85rem !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #e8f0fe !important;
        font-size: 1.4rem !important;
        font-weight: 700 !important;
    }
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        font-weight: 600;
    }
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1b2a 0%, #1b2838 100%);
    }
    /* Dataframes */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# PLOTLY THEME
# ═══════════════════════════════════════════════════════════════
PLOT_TEMPLATE = "plotly_dark"
COLOR_INGRESOS = "#00d4aa"
COLOR_EGRESOS = "#ff6b6b"
COLOR_NETO = "#4ecdc4"
COLOR_PALETTE = px.colors.qualitative.Set2


def styled_bar(fig, money_axis="y"):
    """money_axis: 'y', 'x', 'both', or None."""
    fmt = "$,.0f"
    ya = dict(tickformat=fmt) if money_axis in ("y", "both") else {}
    xa = dict(tickformat=fmt) if money_axis in ("x", "both") else {}
    fig.update_layout(
        template=PLOT_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c8d6e5"),
        margin=dict(l=60, r=20, t=40, b=40),
        legend=dict(orientation="h", y=-0.15),
        yaxis=ya,
        xaxis=xa,
    )
    return fig


def styled_line(fig, money_axis="y"):
    fmt = "$,.0f"
    ya = dict(tickformat=fmt) if money_axis in ("y", "both") else {}
    xa = dict(tickformat=fmt) if money_axis in ("x", "both") else {}
    fig.update_layout(
        template=PLOT_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c8d6e5"),
        margin=dict(l=60, r=20, t=40, b=40),
        yaxis=ya,
        xaxis=xa,
    )
    return fig


# ═══════════════════════════════════════════════════════════════
# SIDEBAR: CARGA DE DATOS
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 📥 Datos")
    uploaded = st.file_uploader("Sube tu Excel", type=["xlsx", "xls"])
    default_path = "prueba.xlsx"
    use_default = st.checkbox(
        "Usar archivo local (prueba.xlsx)",
        value=(uploaded is None),
    )

path = uploaded if uploaded is not None else (default_path if use_default else None)

if path is None:
    st.warning("Sube un archivo Excel o activa el archivo local.")
    st.stop()


@st.cache_data(show_spinner="Cargando datos...")
def load_all(file_path):
    df_i = load_ingresos(file_path)
    df_e = load_egresos(file_path)
    return df_i, df_e


try:
    df_ing_raw, df_egr_raw = load_all(path)
except Exception as e:
    st.error(f"Error al cargar datos: {e}")
    st.stop()

if len(df_ing_raw) == 0 and len(df_egr_raw) == 0:
    st.warning("No se encontraron datos en el archivo.")
    st.stop()

# Agregar YEARWEEK
df_ing_raw = add_yearweek(df_ing_raw)
df_egr_raw = add_yearweek(df_egr_raw)

# ═══════════════════════════════════════════════════════════════
# SIDEBAR: FILTROS
# ═══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("---")
    st.markdown("## 🎛️ Filtros")

    # Año
    all_years = sorted(set(
        list(df_ing_raw["año"].dropna().unique()) +
        list(df_egr_raw["año"].dropna().unique())
    ))
    if len(all_years) == 0:
        st.error("No hay años válidos.")
        st.stop()

    años_sel = st.multiselect("Año", options=all_years, default=all_years)
    if not años_sel:
        st.warning("Selecciona al menos un año.")
        st.stop()

    # Filtrar por año
    df_ing = df_ing_raw[df_ing_raw["año"].isin(años_sel)].copy()
    df_egr = df_egr_raw[df_egr_raw["año"].isin(años_sel)].copy()

    # Rango de semanas (basado en ingresos + egresos)
    all_yw = sorted(set(
        df_ing["YEARWEEK"].dropna().astype(int).tolist() +
        df_egr["YEARWEEK"].dropna().astype(int).tolist()
    ))
    if len(all_yw) > 0:
        yw_labels = [yearweek_label(k) for k in all_yw]
        label_map = dict(zip(yw_labels, all_yw))

        if len(yw_labels) == 1:
            st.info(f"Semana: {yw_labels[0]}")
            yw_start, yw_end = all_yw[0], all_yw[0]
        else:
            lbl_start, lbl_end = st.select_slider(
                "Rango de semanas",
                options=yw_labels,
                value=(yw_labels[0], yw_labels[-1]),
            )
            yw_start, yw_end = label_map[lbl_start], label_map[lbl_end]
            if yw_start > yw_end:
                yw_start, yw_end = yw_end, yw_start

        df_ing = df_ing[
            (df_ing["YEARWEEK"].notna()) &
            (df_ing["YEARWEEK"] >= yw_start) &
            (df_ing["YEARWEEK"] <= yw_end)
        ]
        df_egr = df_egr[
            (df_egr["YEARWEEK"].notna()) &
            (df_egr["YEARWEEK"] >= yw_start) &
            (df_egr["YEARWEEK"] <= yw_end)
        ]

    # Filtro socio
    socios_all = sorted(set(
        [str(x) for x in df_ing["socio"].dropna().unique()] +
        [str(x) for x in df_egr["socio"].dropna().unique()]
    ))
    if socios_all:
        socio_sel = st.multiselect("Socio", options=socios_all, default=socios_all)
        if socio_sel:
            df_ing = df_ing[df_ing["socio"].astype(str).isin(socio_sel)]
            df_egr = df_egr[df_egr["socio"].astype(str).isin(socio_sel)]

    # Filtro conductor
    conductores_all = sorted(set(
        [str(x) for x in df_ing["conductor"].dropna().unique()]
    ))
    if conductores_all:
        search_cond = st.text_input("Buscar conductor")
        if search_cond.strip():
            patt = re.escape(search_cond.strip())
            conductores_f = [c for c in conductores_all if re.search(patt, c, re.IGNORECASE)]
        else:
            conductores_f = conductores_all
        cond_sel = st.multiselect("Conductor", options=conductores_f, default=conductores_f)
        if cond_sel:
            df_ing = df_ing[df_ing["conductor"].astype(str).isin(cond_sel)]


# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════
st.markdown("# 🚗 Dashboard Operación UBER")
st.caption(f"Datos cargados: **{len(df_ing):,}** registros de ingresos · **{len(df_egr):,}** registros de egresos")

# ═══════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════
tab_ingresos, tab_egresos, tab_resumen, tab_vehiculos = st.tabs([
    "💰 Ingresos",
    "💸 Egresos",
    "📊 Resumen Global",
    "🚗 Vehículos",
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: INGRESOS
# ═══════════════════════════════════════════════════════════════
with tab_ingresos:
    st.subheader("💰 Ingresos — Vista General")

    if len(df_ing) == 0:
        st.info("No hay datos de ingresos con los filtros actuales.")
    else:
        # KPIs
        total_renta = df_ing["renta_semanal"].sum()
        total_fianza = df_ing["fianza"].sum()
        total_multa = df_ing["multa"].sum()
        total_hojalatero = df_ing["hojalatero"].sum()
        total_descuentos = df_ing["descuentos"].sum()
        total_ganancias = df_ing["ganancias_totales"].sum()

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Renta Total", f"${total_renta:,.0f}")
        k2.metric("Fianza Neta", f"${total_fianza:,.0f}")
        k3.metric("Multas", f"${total_multa:,.0f}")
        k4.metric("Hojalatero", f"${total_hojalatero:,.0f}")
        k5.metric("Descuentos", f"${total_descuentos:,.0f}")
        k6.metric("Ganancias Totales", f"${total_ganancias:,.0f}")

        st.divider()

        # Gráficas
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("#### Renta Semanal por Semana")
            g = (
                df_ing.groupby("WEEK_LABEL", as_index=False)["renta_semanal"]
                .sum()
                .sort_values("WEEK_LABEL")
            )
            fig = px.bar(
                g, x="WEEK_LABEL", y="renta_semanal",
                color_discrete_sequence=[COLOR_INGRESOS],
            )
            fig.update_traces(hovertemplate="Semana: %{x}<br>Renta: $%{y:,.0f}<extra></extra>")
            fig.update_layout(xaxis_title="Semana", yaxis_title="Renta ($)")
            st.plotly_chart(styled_bar(fig), use_container_width=True)

        with c2:
            st.markdown("#### Ganancias Totales por Semana")
            g2 = (
                df_ing.groupby("WEEK_LABEL", as_index=False)["ganancias_totales"]
                .sum()
                .sort_values("WEEK_LABEL")
            )
            fig2 = px.line(
                g2, x="WEEK_LABEL", y="ganancias_totales",
                markers=True,
                color_discrete_sequence=[COLOR_NETO],
            )
            fig2.update_traces(hovertemplate="Semana: %{x}<br>Ganancias: $%{y:,.0f}<extra></extra>")
            fig2.update_layout(xaxis_title="Semana", yaxis_title="Ganancias ($)")
            st.plotly_chart(styled_line(fig2), use_container_width=True)

        # Renta por conductor (top 15)
        st.markdown("#### Top 15 Conductores — Renta Acumulada")
        top_cond = (
            df_ing.groupby("conductor", as_index=False)["renta_semanal"]
            .sum()
            .sort_values("renta_semanal", ascending=True)
            .tail(15)
        )
        fig3 = px.bar(
            top_cond, x="renta_semanal", y="conductor",
            orientation="h",
            color_discrete_sequence=[COLOR_INGRESOS],
        )
        fig3.update_traces(
            texttemplate="$%{x:,.0f}", textposition="outside",
            hovertemplate="%{y}<br>Renta: $%{x:,.0f}<extra></extra>",
        )
        fig3.update_layout(xaxis_title="Renta ($)", yaxis_title="")
        st.plotly_chart(styled_bar(fig3, money_axis="x"), use_container_width=True)

        # Distribución de conceptos
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("#### Distribución de Conceptos de Ingreso")
            conc = df_ing["concepto_ingreso"].value_counts().reset_index()
            conc.columns = ["Concepto", "Registros"]
            fig4 = px.pie(
                conc.head(8), values="Registros", names="Concepto",
                color_discrete_sequence=COLOR_PALETTE,
                hole=0.4,
            )
            fig4.update_layout(
                template=PLOT_TEMPLATE,
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c8d6e5"),
            )
            st.plotly_chart(fig4, use_container_width=True)

        with c4:
            st.markdown("#### Fianza Neta por Semana")
            g_fi = (
                df_ing.groupby("WEEK_LABEL", as_index=False)["fianza"]
                .sum()
                .sort_values("WEEK_LABEL")
            )
            fig5 = px.bar(
                g_fi, x="WEEK_LABEL", y="fianza",
                color_discrete_sequence=["#ffd93d"],
            )
            fig5.update_traces(hovertemplate="Semana: %{x}<br>Fianza: $%{y:,.0f}<extra></extra>")
            fig5.update_layout(xaxis_title="Semana", yaxis_title="Fianza Neta ($)")
            st.plotly_chart(styled_bar(fig5), use_container_width=True)

        # Tabla detalle
        st.markdown("#### 📋 Tabla de Detalle — Ingresos")
        cols_show = [
            c for c in [
                "año", "semana", "WEEK_LABEL", "conductor", "llave", "socio",
                "app", "renta_semanal", "fianza", "multa", "hojalatero",
                "descuentos", "ganancias_totales", "concepto_ingreso",
            ] if c in df_ing.columns
        ]
        st.dataframe(
            df_ing[cols_show].sort_values(["año", "semana"], ascending=[True, True]),
            use_container_width=True,
            hide_index=True,
            height=400,
            column_config={
                "renta_semanal": st.column_config.NumberColumn("Renta", format="$%,.0f"),
                "fianza": st.column_config.NumberColumn("Fianza", format="$%,.0f"),
                "multa": st.column_config.NumberColumn("Multa", format="$%,.0f"),
                "hojalatero": st.column_config.NumberColumn("Hojalatero", format="$%,.0f"),
                "descuentos": st.column_config.NumberColumn("Descuentos", format="$%,.0f"),
                "ganancias_totales": st.column_config.NumberColumn("Gan. Totales", format="$%,.0f"),
            },
        )


# ═══════════════════════════════════════════════════════════════
# TAB 2: EGRESOS
# ═══════════════════════════════════════════════════════════════
with tab_egresos:
    st.subheader("💸 Egresos — Vista General")

    if len(df_egr) == 0:
        st.info("No hay datos de egresos con los filtros actuales.")
    else:
        # KPIs
        total_gasto = df_egr["monto_real"].sum()
        n_semanas_egr = df_egr["YEARWEEK"].nunique()
        prom_semanal = total_gasto / max(n_semanas_egr, 1)
        top_concepto = (
            df_egr.groupby("concepto", as_index=False)["monto_real"].sum()
            .sort_values("monto_real", ascending=False)
            .iloc[0] if "concepto" in df_egr.columns and len(df_egr) > 0 else None
        )

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Gasto Total", f"${total_gasto:,.0f}")
        k2.metric("Promedio Semanal", f"${prom_semanal:,.0f}")
        k3.metric("Semanas", f"{n_semanas_egr}")
        if top_concepto is not None:
            k4.metric(f"Top: {top_concepto['concepto']}", f"${top_concepto['monto_real']:,.0f}")

        st.divider()

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("#### Gasto por Concepto (General)")
            if "concepto" in df_egr.columns:
                by_conc = (
                    df_egr.groupby("concepto", as_index=False)["monto_real"]
                    .sum()
                    .sort_values("monto_real", ascending=True)
                    .tail(15)
                )
                fig = px.bar(
                    by_conc, x="monto_real", y="concepto",
                    orientation="h",
                    color_discrete_sequence=[COLOR_EGRESOS],
                )
                fig.update_traces(
                    texttemplate="$%{x:,.0f}", textposition="outside",
                    hovertemplate="%{y}<br>Gasto: $%{x:,.0f}<extra></extra>",
                )
                fig.update_layout(xaxis_title="Gasto ($)", yaxis_title="")
                st.plotly_chart(styled_bar(fig, money_axis="x"), use_container_width=True)

        with c2:
            st.markdown("#### Gasto Semanal")
            g_egr = (
                df_egr.groupby("WEEK_LABEL", as_index=False)["monto_real"]
                .sum()
                .sort_values("WEEK_LABEL")
            )
            fig2 = px.line(
                g_egr, x="WEEK_LABEL", y="monto_real",
                markers=True,
                color_discrete_sequence=[COLOR_EGRESOS],
            )
            fig2.update_traces(hovertemplate="Semana: %{x}<br>Gasto: $%{y:,.0f}<extra></extra>")
            fig2.update_layout(xaxis_title="Semana", yaxis_title="Gasto ($)")
            st.plotly_chart(styled_line(fig2), use_container_width=True)

        # Detalle por tipo
        if "detalle" in df_egr.columns:
            st.markdown("#### Gasto por Detalle (Particular)")
            by_det = (
                df_egr.groupby("detalle", as_index=False)["monto_real"]
                .sum()
                .sort_values("monto_real", ascending=False)
                .head(20)
            )
            fig3 = px.bar(
                by_det, x="detalle", y="monto_real",
                color_discrete_sequence=[COLOR_EGRESOS],
            )
            fig3.update_traces(
                texttemplate="$%{y:,.0f}", textposition="outside",
                hovertemplate="%{x}<br>Gasto: $%{y:,.0f}<extra></extra>",
            )
            fig3.update_layout(xaxis_title="Detalle", yaxis_title="Gasto ($)")
            st.plotly_chart(styled_bar(fig3), use_container_width=True)

        # Tabla detalle
        st.markdown("#### 📋 Tabla de Detalle — Egresos")
        cols_egr = [
            c for c in [
                "año", "semana", "WEEK_LABEL", "concepto", "detalle",
                "conductor", "llave", "socio", "metodo_pago",
                "monto_real", "comercio",
            ] if c in df_egr.columns
        ]
        st.dataframe(
            df_egr[cols_egr].sort_values(["año", "semana"], ascending=[True, True]),
            use_container_width=True,
            hide_index=True,
            height=400,
            column_config={
                "monto_real": st.column_config.NumberColumn("Monto Real", format="$%,.0f"),
            },
        )


# ═══════════════════════════════════════════════════════════════
# TAB 3: RESUMEN GLOBAL
# ═══════════════════════════════════════════════════════════════
with tab_resumen:
    st.subheader("📊 Resumen Global — Ingresos vs Egresos")

    total_ing = df_ing["ganancias_totales"].sum() if len(df_ing) > 0 else 0
    total_egr = df_egr["monto_real"].sum() if len(df_egr) > 0 else 0
    utilidad = total_ing - total_egr

    k1, k2, k3 = st.columns(3)
    k1.metric("Ingresos Totales", f"${total_ing:,.0f}")
    k2.metric("Egresos Totales", f"${total_egr:,.0f}")
    k3.metric(
        "Utilidad Neta",
        f"${utilidad:,.0f}",
        delta=f"{'✅' if utilidad >= 0 else '⚠️'} {'Positiva' if utilidad >= 0 else 'Negativa'}",
    )

    st.divider()

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### Ingreso vs Egreso por Semana")

        # Agrupar ingresos por semana
        if len(df_ing) > 0:
            gi = (
                df_ing.groupby(["YEARWEEK", "WEEK_LABEL"], as_index=False)["ganancias_totales"]
                .sum()
                .rename(columns={"ganancias_totales": "Ingresos"})
            )
        else:
            gi = pd.DataFrame(columns=["YEARWEEK", "WEEK_LABEL", "Ingresos"])

        if len(df_egr) > 0:
            ge = (
                df_egr.groupby(["YEARWEEK", "WEEK_LABEL"], as_index=False)["monto_real"]
                .sum()
                .rename(columns={"monto_real": "Egresos"})
            )
        else:
            ge = pd.DataFrame(columns=["YEARWEEK", "WEEK_LABEL", "Egresos"])

        # Merge
        merged = pd.merge(gi, ge, on=["YEARWEEK", "WEEK_LABEL"], how="outer").fillna(0)
        merged = merged.sort_values("YEARWEEK")

        if len(merged) > 0:
            m = merged.melt(
                id_vars="WEEK_LABEL",
                value_vars=["Ingresos", "Egresos"],
                var_name="Tipo", value_name="Monto",
            )
            fig = px.bar(
                m, x="WEEK_LABEL", y="Monto", color="Tipo",
                barmode="group",
                color_discrete_map={"Ingresos": COLOR_INGRESOS, "Egresos": COLOR_EGRESOS},
            )
            fig.update_traces(hovertemplate="%{x}<br>%{data.name}: $%{y:,.0f}<extra></extra>")
            fig.update_layout(xaxis_title="Semana", yaxis_title="Monto ($)")
            st.plotly_chart(styled_bar(fig), use_container_width=True)

    with c2:
        st.markdown("#### Distribución de Egresos por Concepto")
        if len(df_egr) > 0 and "concepto" in df_egr.columns:
            conc_egr = (
                df_egr.groupby("concepto", as_index=False)["monto_real"]
                .sum()
                .sort_values("monto_real", ascending=False)
            )
            fig2 = px.pie(
                conc_egr.head(10), values="monto_real", names="concepto",
                color_discrete_sequence=COLOR_PALETTE,
                hole=0.45,
            )
            fig2.update_layout(
                template=PLOT_TEMPLATE,
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c8d6e5"),
            )
            st.plotly_chart(fig2, use_container_width=True)

    # Utilidad por semana
    st.markdown("#### Utilidad Neta por Semana")
    if len(merged) > 0:
        merged["Utilidad"] = merged["Ingresos"] - merged["Egresos"]
        colors = [COLOR_INGRESOS if v >= 0 else COLOR_EGRESOS for v in merged["Utilidad"]]

        fig3 = go.Figure(go.Bar(
            x=merged["WEEK_LABEL"],
            y=merged["Utilidad"],
            marker_color=colors,
            text=[f"${v:,.0f}" for v in merged["Utilidad"]],
            textposition="outside",
        ))
        fig3.update_layout(
            xaxis_title="Semana", yaxis_title="Utilidad ($)",
        )
        st.plotly_chart(styled_bar(fig3), use_container_width=True)

    # Tabla resumen por semana
    st.markdown("#### 📋 Resumen por Semana")
    if len(merged) > 0:
        merged_show = merged[["WEEK_LABEL", "Ingresos", "Egresos", "Utilidad"]].copy()
        merged_show = merged_show.sort_values("WEEK_LABEL")
        st.dataframe(
            merged_show,
            use_container_width=True,
            hide_index=True,
            height=350,
            column_config={
                "WEEK_LABEL": st.column_config.TextColumn("Semana"),
                "Ingresos": st.column_config.NumberColumn(format="$%,.0f"),
                "Egresos": st.column_config.NumberColumn(format="$%,.0f"),
                "Utilidad": st.column_config.NumberColumn(format="$%,.0f"),
            },
        )


# ═══════════════════════════════════════════════════════════════
# TAB 4: VEHÍCULOS
# ═══════════════════════════════════════════════════════════════
with tab_vehiculos:
    st.subheader("🚗 Análisis por Vehículo")

    if len(df_ing) == 0:
        st.info("No hay datos de ingresos para analizar vehículos.")
    else:
        # Selector de llaves
        llaves = sorted([str(x) for x in df_ing["llave"].dropna().unique() if str(x) != "-"])

        search_ll = st.text_input("🔍 Buscar vehículo (llave)", key="veh_search")
        if search_ll.strip():
            patt = re.escape(search_ll.strip())
            llaves_f = [l for l in llaves if re.search(patt, l, re.IGNORECASE)]
        else:
            llaves_f = llaves

        llave_sel = st.multiselect(
            "Selecciona vehículo(s)",
            options=llaves_f,
            default=llaves_f[:3] if len(llaves_f) > 0 else [],
            key="veh_llave",
        )

        if not llave_sel:
            st.info("Selecciona al menos un vehículo para ver el análisis.")
        else:
            df_v = df_ing[df_ing["llave"].astype(str).isin(llave_sel)].copy()

            # KPI por vehículo
            st.markdown("#### Rendimiento por Vehículo")
            kpi_v = (
                df_v.groupby("llave", as_index=False)
                .agg(
                    Renta=("renta_semanal", "sum"),
                    Fianza=("fianza", "sum"),
                    Multas=("multa", "sum"),
                    Hojalatero=("hojalatero", "sum"),
                    Ganancias=("ganancias_totales", "sum"),
                    Semanas=("semana", "nunique"),
                )
                .sort_values("Ganancias", ascending=False)
            )

            # Agregar egresos por vehículo si existen
            if len(df_egr) > 0 and "llave" in df_egr.columns:
                egr_v = (
                    df_egr[df_egr["llave"].astype(str).isin(llave_sel)]
                    .groupby("llave", as_index=False)["monto_real"]
                    .sum()
                    .rename(columns={"monto_real": "Egresos"})
                )
                kpi_v = kpi_v.merge(egr_v, on="llave", how="left").fillna(0)
                kpi_v["Utilidad"] = kpi_v["Ganancias"] - kpi_v["Egresos"]

            st.dataframe(
                kpi_v,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "llave": st.column_config.TextColumn("Vehículo"),
                    "Renta": st.column_config.NumberColumn(format="$%,.0f"),
                    "Fianza": st.column_config.NumberColumn(format="$%,.0f"),
                    "Multas": st.column_config.NumberColumn(format="$%,.0f"),
                    "Hojalatero": st.column_config.NumberColumn(format="$%,.0f"),
                    "Ganancias": st.column_config.NumberColumn(format="$%,.0f"),
                    "Egresos": st.column_config.NumberColumn(format="$%,.0f"),
                    "Utilidad": st.column_config.NumberColumn(format="$%,.0f"),
                },
            )

            st.divider()

            # Gráfica temporal por vehículo
            st.markdown("#### Rendimiento Semanal por Vehículo")
            metric_opt = st.radio(
                "Métrica:",
                ["Ganancias Totales", "Renta Semanal", "Fianza"],
                horizontal=True,
            )
            ycol_map = {
                "Ganancias Totales": "ganancias_totales",
                "Renta Semanal": "renta_semanal",
                "Fianza": "fianza",
            }
            ycol = ycol_map[metric_opt]

            g_v = (
                df_v.groupby(["YEARWEEK", "WEEK_LABEL", "llave"], as_index=False)[ycol]
                .sum()
                .sort_values(["YEARWEEK", "llave"])
            )
            fig = px.line(
                g_v, x="WEEK_LABEL", y=ycol, color="llave",
                markers=True,
                color_discrete_sequence=COLOR_PALETTE,
            )
            fig.update_traces(hovertemplate="Semana: %{x}<br>$%{y:,.0f}<extra></extra>")
            fig.update_layout(xaxis_title="Semana", yaxis_title=metric_opt)
            st.plotly_chart(styled_line(fig), use_container_width=True)

            # Historial de egresos por vehículo
            if len(df_egr) > 0 and "llave" in df_egr.columns:
                df_egr_v = df_egr[df_egr["llave"].astype(str).isin(llave_sel)].copy()
                if len(df_egr_v) > 0:
                    st.markdown("#### Historial de Egresos del Vehículo")
                    cols_ev = [
                        c for c in [
                            "año", "semana", "WEEK_LABEL", "concepto", "detalle",
                            "llave", "conductor", "monto_real", "comercio",
                        ] if c in df_egr_v.columns
                    ]
                    st.dataframe(
                        df_egr_v[cols_ev].sort_values(["año", "semana"]),
                        use_container_width=True,
                        hide_index=True,
                        height=350,
                        column_config={
                            "monto_real": st.column_config.NumberColumn("Monto", format="$%,.0f"),
                        },
                    )

            # Detalle ingresos
            st.markdown("#### 📋 Detalle de Ingresos por Vehículo")
            cols_v = [
                c for c in [
                    "año", "semana", "WEEK_LABEL", "conductor", "llave",
                    "renta_semanal", "fianza", "multa", "hojalatero",
                    "descuentos", "ganancias_totales", "concepto_ingreso",
                ] if c in df_v.columns
            ]
            st.dataframe(
                df_v[cols_v].sort_values(["año", "semana"]),
                use_container_width=True,
                hide_index=True,
                height=400,
                column_config={
                    "renta_semanal": st.column_config.NumberColumn("Renta", format="$%,.0f"),
                    "fianza": st.column_config.NumberColumn("Fianza", format="$%,.0f"),
                    "multa": st.column_config.NumberColumn("Multa", format="$%,.0f"),
                    "hojalatero": st.column_config.NumberColumn("Hojalatero", format="$%,.0f"),
                    "descuentos": st.column_config.NumberColumn("Descuentos", format="$%,.0f"),
                    "ganancias_totales": st.column_config.NumberColumn("Gan. Totales", format="$%,.0f"),
                },
            )
