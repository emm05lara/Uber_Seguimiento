# app_dashboard_v4.py
import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px

# =========================
# Config
# =========================
st.set_page_config(page_title="Dashboard Uber", layout="wide")
st.title("📊 Dashboard Operación Uber")
st.caption("Filtros por Año/Semana (ISO) + búsquedas por texto. Incluye vistas por vehículo (Marca/Modelo/Llave).")


# =========================
# Helpers
# =========================
def _strip_unnamed_cols(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]

def _normalize_colnames(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _coerce_numeric_series(s: pd.Series) -> pd.Series:
    """
    Convierte a numérico:
    - Acepta strings con $, comas, paréntesis (negativos), etc.
    """
    if s is None:
        return s
    if pd.api.types.is_numeric_dtype(s):
        return s

    x = s.astype(str).str.strip()
    x = x.replace({"nan": np.nan, "None": np.nan, "": np.nan})

    # (123) -> -123
    x = x.str.replace(r"^\((.*)\)$", r"-\1", regex=True)

    # Quitar símbolos/letras, conservar dígitos, punto, coma, signo
    x = x.str.replace(r"[^0-9,\.\-]", "", regex=True)

    # Comas: si ya hay punto, las comas suelen ser separador de miles -> quitar
    def fix_commas(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return val
        val = str(val)
        if val.count(",") == 0:
            return val
        if val.count(".") >= 1:
            return val.replace(",", "")
        # si no hay punto, asumimos coma como decimal: 12,34 -> 12.34
        return val.replace(",", ".")
    x = x.apply(fix_commas)

    return pd.to_numeric(x, errors="coerce")

def ensure_required_cols(df: pd.DataFrame, required: list[str]) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"Faltan columnas requeridas: {missing}")
        st.stop()

def yearweek_label(yearweek: int) -> str:
    y = int(yearweek // 100)
    w = int(yearweek % 100)
    return f"{y}-W{w:02d}"

def make_yearweek(df: pd.DataFrame) -> pd.Series:
    return df["AÑO"].astype("Int64") * 100 + df["SEM"].astype("Int64")

def searchable_multiselect_filter(frame: pd.DataFrame, label: str, col: str, key_prefix: str, default_all: bool = True) -> pd.DataFrame:
    """
    Multiselect con 'barra de búsqueda' (text_input) para filtrar opciones.
    """
    opts = [str(x) for x in frame[col].dropna().unique()]
    opts = sorted(opts, key=lambda s: s.lower())

    if len(opts) == 0:
        return frame

    search = st.text_input(f"Buscar en {label}", value="", key=f"{key_prefix}_q")
    if search.strip():
        patt = re.escape(search.strip())
        opts_filtered = [o for o in opts if re.search(patt, o, flags=re.IGNORECASE)]
    else:
        opts_filtered = opts

    default = opts if default_all else []
    selected = st.multiselect(label, options=opts_filtered, default=default, key=f"{key_prefix}_ms")

    if not selected:
        return frame.iloc[0:0]

    return frame[frame[col].astype(str).isin(selected)]


# =========================
# Sidebar: Cargar datos
# =========================
with st.sidebar:
    st.header("📥 Datos")
    uploaded = st.file_uploader("Sube tu Excel", type=["xlsx", "xls"])
    default_path = "Libro4.xlsx"
    use_default = st.checkbox("Usar archivo local Libro4.xlsx (si existe)", value=(uploaded is None))

def load_data():
    if uploaded is not None:
        xls = pd.ExcelFile(uploaded)
        sheet = "BASE" if "BASE" in xls.sheet_names else xls.sheet_names[0]
        df_ = pd.read_excel(uploaded, sheet_name=sheet)
        return df_, sheet, "upload"

    if use_default:
        try:
            xls = pd.ExcelFile(default_path)
            sheet = "BASE" if "BASE" in xls.sheet_names else xls.sheet_names[0]
            df_ = pd.read_excel(default_path, sheet_name=sheet)
            return df_, sheet, "local"
        except Exception as e:
            st.error(f"No se pudo abrir {default_path}. Error: {e}")
            st.stop()

    st.warning("Sube un Excel o activa 'usar archivo local'.")
    st.stop()

df_raw, sheet_name, origin = load_data()
df = _strip_unnamed_cols(_normalize_colnames(df_raw.copy()))

# Renombres esperados
rename_map = {}
if "GANANCIAS" in df.columns and "Ganancia" not in df.columns:
    rename_map["GANANCIAS"] = "Ganancia"
if "PLATAFORMA" in df.columns and "Plataforma" not in df.columns:
    rename_map["PLATAFORMA"] = "Plataforma"
if "CUENTA" in df.columns and "Cuenta" not in df.columns:
    rename_map["CUENTA"] = "Cuenta"
if rename_map:
    df = df.rename(columns=rename_map)

# =========================
# Validaciones y tipos
# =========================
required_cols = [
    "SEM", "MES", "AÑO",
    "CONDUCTOR", "TIPO", "AGRUPADOR", "CONCEPTO",
    "LLAVE", "MARCA", "MODELO", "COLOR", "SOCIO",
    "Plataforma", "Cuenta", "Ganancia", "FIANZA"
]
ensure_required_cols(df, required_cols)

# Tipos numéricos
for col in ["Plataforma", "Cuenta", "Ganancia", "FIANZA"]:
    df[col] = _coerce_numeric_series(df[col])

# AÑO / SEM a enteros si se puede
df["AÑO"] = pd.to_numeric(df["AÑO"], errors="coerce").astype("Int64")
df["SEM"] = pd.to_numeric(df["SEM"], errors="coerce").astype("Int64")

# =========================
# Tabs
# =========================
tab_general, tab_vehiculos = st.tabs(["📌 Dashboard general", "🚗 Vehículos"])

# =========================
# Filtros comunes (sidebar)
# =========================
with st.sidebar:
    st.header("🎛️ Filtros")

    years = sorted([int(y) for y in df["AÑO"].dropna().unique()])
    if len(years) == 0:
        st.error("No hay valores válidos en AÑO.")
        st.stop()

    if len(years) == 1:
        y_selected = years
        st.info(f"Mostrando año: {years[0]}")
    else:
        y_selected = st.multiselect("Año (AÑO)", options=years, default=years)
        if not y_selected:
            st.warning("Selecciona al menos un año.")
            st.stop()

    # Rango de semanas (DISCRETO: AÑO-SEM, sin depender de días)
    df_f = df[df["AÑO"].isin(y_selected)].copy()

    # Solo combinaciones válidas AÑO/SEM
    weeks_tbl = (
        df_f.dropna(subset=["AÑO", "SEM"])
        .assign(YEARWEEK=lambda x: make_yearweek(x))
        .dropna(subset=["YEARWEEK"])
        .drop_duplicates(subset=["YEARWEEK"])
        .sort_values("YEARWEEK")
    )
    if len(weeks_tbl) > 0:
        weeks_tbl["LABEL"] = weeks_tbl["YEARWEEK"].astype(int).map(yearweek_label)
        week_labels = weeks_tbl["LABEL"].tolist()
        label_to_key = dict(zip(weeks_tbl["LABEL"], weeks_tbl["YEARWEEK"].astype(int)))

        if len(week_labels) == 1:
            st.info(f"Semana disponible: {week_labels[0]}")
            w_start_label, w_end_label = week_labels[0], week_labels[0]
        else:
            w_start_label, w_end_label = st.select_slider(
                "Rango de semanas (ISO)",
                options=week_labels,
                value=(week_labels[0], week_labels[-1]),
            )

        w_start_key = int(label_to_key[w_start_label])
        w_end_key = int(label_to_key[w_end_label])
        if w_start_key > w_end_key:
            w_start_key, w_end_key = w_end_key, w_start_key

        df_f["YEARWEEK"] = make_yearweek(df_f)
        df_f = df_f[(df_f["YEARWEEK"].notna()) & (df_f["YEARWEEK"] >= w_start_key) & (df_f["YEARWEEK"] <= w_end_key)]
        df_f["WEEK_LABEL"] = df_f["YEARWEEK"].astype(int).map(yearweek_label)
    else:
        st.warning("No hay combinaciones válidas AÑO/SEM para el/los años seleccionados.")
        df_f = df_f.iloc[0:0].copy()

    # --- PRIMER FILTRO: LLAVE
    df_f = searchable_multiselect_filter(df_f, "Llave (vehículo)", "LLAVE", "llave")

    # Resto de filtros (con búsqueda)
    df_f = searchable_multiselect_filter(df_f, "Marca", "MARCA", "marca")
    df_f = searchable_multiselect_filter(df_f, "Modelo", "MODELO", "modelo")
    df_f = searchable_multiselect_filter(df_f, "Conductor", "CONDUCTOR", "conductor")
    df_f = searchable_multiselect_filter(df_f, "Tipo", "TIPO", "tipo")
    df_f = searchable_multiselect_filter(df_f, "Agrupador", "AGRUPADOR", "agrupador")
    df_f = searchable_multiselect_filter(df_f, "Concepto", "CONCEPTO", "concepto")
    df_f = searchable_multiselect_filter(df_f, "Socio", "SOCIO", "socio")


# =========================
# Métricas auxiliares
# =========================
def add_income_expense(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["Ingreso"] = out["Ganancia"].where(out["Ganancia"] > 0, 0.0)
    out["Egreso"] = (-out["Ganancia"]).where(out["Ganancia"] < 0, 0.0)
    out["Contribucion"] = out["Ingreso"] - out["Egreso"]  # neto (igual a Ganancia en agregación)
    return out

df_f2 = add_income_expense(df_f)

# =========================
# TAB: General
# =========================
with tab_general:
    st.subheader("📈 KPIs (filtrado)")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Plataforma", f"${df_f2['Plataforma'].sum():,.0f}")
    k2.metric("Cuenta", f"${df_f2['Cuenta'].sum():,.0f}")
    k3.metric("Ganancia (neto)", f"${df_f2['Ganancia'].sum():,.0f}")
    k4.metric("Ingreso", f"${df_f2['Ingreso'].sum():,.0f}")
    k5.metric("Egreso", f"${df_f2['Egreso'].sum():,.0f}")

    st.divider()

    # =========================
    # Gráficas solicitadas
    # =========================
    st.subheader("📊 Gráficas")

    # (1) Barras apiladas (Ganancia vs Cuenta) por semana
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Barras apiladas: Ganancia vs Cuenta (por semana)**")
        if len(df_f2) == 0:
            st.info("No hay datos con los filtros actuales.")
        else:
            g = df_f2.groupby("WEEK_LABEL", as_index=False)[["Ganancia", "Cuenta"]].sum()
            g = g.sort_values("WEEK_LABEL")
            m = g.melt(id_vars="WEEK_LABEL", value_vars=["Ganancia", "Cuenta"], var_name="Serie", value_name="Monto")
            fig = px.bar(m, x="WEEK_LABEL", y="Monto", color="Serie", barmode="stack")
            fig.update_layout(xaxis_title="Semana", yaxis_title="Monto")
            st.plotly_chart(fig, use_container_width=True)

    # (2) Contribución (Ingreso vs Egreso)
    with c2:
        st.markdown("**Contribución: Ingreso vs Egreso (totales)**")
        totals = pd.DataFrame({
            "Serie": ["Ingreso", "Egreso"],
            "Monto": [df_f2["Ingreso"].sum(), df_f2["Egreso"].sum()]
        })
        fig = px.bar(totals, x="Serie", y="Monto")
        fig.update_layout(xaxis_title="", yaxis_title="Monto")
        st.plotly_chart(fig, use_container_width=True)

    # (3) Gráfica de gasto vs Semana
    st.markdown("**Gasto (Egreso) vs Semana**")
    if len(df_f2) == 0:
        st.info("No hay datos con los filtros actuales.")
    else:
        g = df_f2.groupby("WEEK_LABEL", as_index=False)[["Egreso"]].sum().sort_values("WEEK_LABEL")
        fig = px.line(g, x="WEEK_LABEL", y="Egreso", markers=True)
        fig.update_layout(xaxis_title="Semana", yaxis_title="Egreso")
        st.plotly_chart(fig, use_container_width=True)

    # (4) Detalle de gasto por agrupador (con llave de auto)
    st.markdown("**Detalle de gasto por Agrupador (según Llave seleccionada)**")
    if len(df_f2) == 0:
        st.info("No hay datos con los filtros actuales.")
    else:
        gastos = df_f2[df_f2["Egreso"] > 0].copy()
        if len(gastos) == 0:
            st.info("No hay egresos en el rango/filtros actuales.")
        else:
            by_agr = (
                gastos.groupby(["LLAVE", "AGRUPADOR"], as_index=False)["Egreso"]
                .sum()
                .sort_values("Egreso", ascending=False)
            )

            # Si el usuario eligió varias llaves, mostramos top por llave con un selector rápido
            llaves_disp = sorted([str(x) for x in gastos["LLAVE"].dropna().unique()])
            if len(llaves_disp) == 0:
                st.info("No hay llaves en los datos filtrados.")
            else:
                if len(llaves_disp) == 1:
                    llave_focus = llaves_disp[0]
                else:
                    llave_focus = st.selectbox("Ver detalle para llave:", options=llaves_disp, index=0)

                by_agr_focus = by_agr[by_agr["LLAVE"].astype(str) == str(llave_focus)].head(25)
                fig = px.bar(by_agr_focus, x="AGRUPADOR", y="Egreso")
                fig.update_layout(xaxis_title="Agrupador", yaxis_title="Egreso")
                st.plotly_chart(fig, use_container_width=True)

                # Tabla de detalle (conceptos) para esa llave
                st.markdown("**Conceptos de gasto (detalle)**")
                det = gastos[gastos["LLAVE"].astype(str) == str(llave_focus)].copy()
                det = det.sort_values(["AÑO", "SEM", "Egreso"], ascending=[True, True, False])
                st.dataframe(
                    det[["AÑO","SEM","WEEK_LABEL","LLAVE","MARCA","MODELO","CONDUCTOR","TIPO","AGRUPADOR","CONCEPTO","Egreso","Ganancia"]],
                    use_container_width=True,
                    hide_index=True
                )

    st.divider()
    st.subheader("🧾 Resúmenes")

    r1, r2 = st.columns(2)
    with r1:
        st.markdown("**Por Conductor**")
        if len(df_f2) == 0:
            st.info("Sin datos.")
        else:
            df_by_conductor = (
                df_f2.groupby("CONDUCTOR", as_index=False)[["Ingreso","Egreso","Ganancia","Plataforma","Cuenta","FIANZA"]]
                .sum()
                .sort_values("Ganancia", ascending=False)
            )
            st.dataframe(df_by_conductor, use_container_width=True, hide_index=True)

    with r2:
        st.markdown("**Por Agrupador**")
        if len(df_f2) == 0:
            st.info("Sin datos.")
        else:
            df_by_agr = (
                df_f2.groupby("AGRUPADOR", as_index=False)[["Ingreso","Egreso","Ganancia"]]
                .sum()
                .sort_values("Egreso", ascending=False)
            )
            st.dataframe(df_by_agr, use_container_width=True, hide_index=True)

    st.subheader("🔎 Detalle (filtrado)")
    st.dataframe(
        df_f2.sort_values(["AÑO", "SEM"], ascending=[True, True]),
        use_container_width=True,
        hide_index=True
    )


# =========================
# TAB: Vehículos
# =========================
with tab_vehiculos:
    st.subheader("🚗 Selección por Marca / Modelo / Llave")

    # Dataset base para selección (no uses df_f2, porque aquí queremos una selección más libre)
    dfv = df.copy()
    dfv = add_income_expense(dfv)
    dfv["YEARWEEK"] = make_yearweek(dfv)
    dfv["WEEK_LABEL"] = dfv["YEARWEEK"].dropna().astype(int).map(yearweek_label)

    sel1, sel2, sel3 = st.columns(3)

    with sel1:
        marcas = sorted([str(x) for x in dfv["MARCA"].dropna().unique()])
        q_marca = st.text_input("Buscar Marca", value="", key="veh_q_marca")
        marcas_f = [m for m in marcas if (q_marca.strip() == "" or re.search(re.escape(q_marca.strip()), m, re.IGNORECASE))]
        marca_sel = st.multiselect("Marca", options=marcas_f, default=marcas_f, key="veh_marca")
    with sel2:
        tmp = dfv.copy()
        if marca_sel:
            tmp = tmp[tmp["MARCA"].astype(str).isin([str(x) for x in marca_sel])]
        modelos = sorted([str(x) for x in tmp["MODELO"].dropna().unique()])
        q_modelo = st.text_input("Buscar Modelo", value="", key="veh_q_modelo")
        modelos_f = [m for m in modelos if (q_modelo.strip() == "" or re.search(re.escape(q_modelo.strip()), m, re.IGNORECASE))]
        modelo_sel = st.multiselect("Modelo", options=modelos_f, default=modelos_f, key="veh_modelo")
    with sel3:
        tmp2 = tmp.copy()
        if modelo_sel:
            tmp2 = tmp2[tmp2["MODELO"].astype(str).isin([str(x) for x in modelo_sel])]
        llaves = sorted([str(x) for x in tmp2["LLAVE"].dropna().unique()])
        q_llave = st.text_input("Buscar Llave", value="", key="veh_q_llave")
        llaves_f = [m for m in llaves if (q_llave.strip() == "" or re.search(re.escape(q_llave.strip()), m, re.IGNORECASE))]
        llave_sel = st.multiselect("Llave", options=llaves_f, default=llaves_f[:1] if len(llaves_f)>0 else [], key="veh_llave")

    if not llave_sel:
        st.info("Selecciona al menos una **Llave** para ver métricas por vehículo.")
    else:
        dfveh = dfv[dfv["LLAVE"].astype(str).isin([str(x) for x in llave_sel])].copy()

        # KPI por vehículo
        st.subheader("📌 Vista de ingreso, gasto y contribución (por vehículo)")
        kpi = (
            dfveh.groupby(["LLAVE","MARCA","MODELO"], as_index=False)[["Ingreso","Egreso","Ganancia"]]
            .sum()
            .sort_values("Ganancia", ascending=False)
        )
        st.dataframe(kpi, use_container_width=True, hide_index=True)

        # Serie temporal por semana (por vehículo)
        st.markdown("**Ingreso / Egreso / Neto por semana**")
        g = (
            dfveh.groupby(["WEEK_LABEL","LLAVE"], as_index=False)[["Ingreso","Egreso","Ganancia"]]
            .sum()
        )
        g = g.sort_values(["WEEK_LABEL","LLAVE"])

        metric_choice = st.radio("Serie a graficar:", ["Ganancia (neto)", "Ingreso", "Egreso"], horizontal=True)
        ycol = {"Ganancia (neto)":"Ganancia","Ingreso":"Ingreso","Egreso":"Egreso"}[metric_choice]
        fig = px.line(g, x="WEEK_LABEL", y=ycol, color="LLAVE", markers=True)
        fig.update_layout(xaxis_title="Semana", yaxis_title=ycol)
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Detalle por vehículo (filtrado por selección de vehículos)**")
        st.dataframe(
            dfveh.sort_values(["AÑO","SEM","LLAVE"], ascending=[True, True, True])[[
                "AÑO","SEM","WEEK_LABEL","LLAVE","MARCA","MODELO","CONDUCTOR","TIPO","AGRUPADOR","CONCEPTO",
                "Ingreso","Egreso","Ganancia","Plataforma","Cuenta","FIANZA"
            ]],
            use_container_width=True,
            hide_index=True
        )
