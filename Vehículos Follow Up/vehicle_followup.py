import os
import re
import base64
import unicodedata
from datetime import date

import pandas as pd
import streamlit as st

# =========================
# Config
# =========================
st.set_page_config(page_title="Flota - Cards & Alertas", layout="wide")

EXCEL_PATH_DEFAULT = "S51 AUTOS ASHC.xlsx"
SHEET_NAME = "GENERAL"

IMAGES_DIR_DEFAULT = "images"  # fotos del VEHÍCULO (por PLACAS)
IMAGES_CONDUCTOR_DIR_DEFAULT = "images_conductor"  # fotos del CONDUCTOR (por nombre normalizado)

# =========================
# Utils
# =========================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def coerce_money_column(df: pd.DataFrame, col: str) -> pd.Series:
    """Convierte una columna de dinero a numérico.
    Si el Excel separa el '$' y el número en columnas contiguas, intenta leer el número de la columna siguiente.
    """
    if col not in df.columns:
        return pd.Series([pd.NA] * len(df), index=df.index)

    s = df[col]

    # 1) Si ya hay números, úsalo
    s_num = pd.to_numeric(s, errors="coerce")
    if s_num.notna().any():
        return s_num

    # 2) Intentar limpiar texto en la misma columna
    s_txt = (
        s.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )
    s_txt_num = pd.to_numeric(s_txt, errors="coerce")
    if s_txt_num.notna().any():
        return s_txt_num

    # 3) Caso típico: '$' en esta col y el número en la siguiente
    try:
        idx = list(df.columns).index(col)
        if idx + 1 < len(df.columns):
            s2 = df.iloc[:, idx + 1]
            s2_txt = (
                s2.astype(str)
                .str.replace("$", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip()
            )
            s2_num = pd.to_numeric(s2_txt, errors="coerce")
            return s2_num
    except Exception:
        pass

    return pd.to_numeric(s_txt, errors="coerce")


def parse_mixed_date(x):
    return pd.to_datetime(x, errors="coerce", dayfirst=True)

def safe_str(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()

def is_checkmark(x) -> bool:
    s = safe_str(x).upper()
    return s in {"✔", "SI", "SÍ", "OK", "PAGADO", "AL CORRIENTE", "TRUE", "1", "X"}

def is_verified(x) -> bool:
    s = safe_str(x).upper()
    return ("VERIFICADO" in s) or (s in {"SI", "SÍ", "OK", "TRUE", "1"})

def has_debt(x) -> bool:
    s = safe_str(x).upper()
    return s not in {"", "SIN", "NO", "0", "N/A", "SIN ADEUDO"} and s != "SIN ADEUDO"

def load_data(excel_path: str, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    df = normalize_columns(df)

    # Fechas relevantes (según tu archivo)
    df["VIGENCIA_DT"] = parse_mixed_date(df["VIGENCIA"]) if "VIGENCIA" in df.columns else pd.NaT
    df["TCIRC_DT"] = parse_mixed_date(df["T. CIRC. (VIGENCIA"]) if "T. CIRC. (VIGENCIA" in df.columns else pd.NaT
    df["FECHA_COMPRA_DT"] = parse_mixed_date(df["FECHA COMPRA"]) if "FECHA COMPRA" in df.columns else pd.NaT

    # Columnas de dinero (robusto para Excel con '$' separado)
    df["IMPORTE_COMPRA_NUM"] = coerce_money_column(df, "IMPORTE")
    df["CUENTA_NUM"] = coerce_money_column(df, "CUENTA") if "CUENTA" in df.columns else pd.Series([pd.NA]*len(df), index=df.index)

    # Flags KPI
    df["FLAG_VERIFICADO"] = df["VERIFICACIÓN"].apply(is_verified) if "VERIFICACIÓN" in df.columns else False
    df["FLAG_TENENCIA_OK"] = df["TENENCIA"].apply(is_checkmark) if "TENENCIA" in df.columns else False
    df["FLAG_ADEUDO"] = df["ADEUDO"].apply(has_debt) if "ADEUDO" in df.columns else False

    return df

def days_to(d: pd.Timestamp):
    if pd.isna(d):
        return None
    return (d.date() - date.today()).days

def alert_label(days, warn_days: int):
    if days is None:
        return ("Sin fecha", "badge-muted")
    if days < 0:
        return (f"Vencido ({abs(days)}d)", "badge-danger")
    if days <= warn_days:
        return (f"Por vencer ({days}d)", "badge-warn")
    return (f"Vigente ({days}d)", "badge-ok")

def find_image_for_plate(plate: str, images_dir: str):
    plate = safe_str(plate)
    if not plate:
        return None
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = os.path.join(images_dir, f"{plate}.{ext}")
        if os.path.exists(p):
            return p
    return None

def normalize_filename(name: str) -> str:
    """
    Normaliza un texto para usarlo como nombre de archivo:
    - quita acentos
    - minúsculas
    - espacios -> _
    - elimina caracteres raros
    """
    name = safe_str(name)
    if not name:
        return ""
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ascii", "ignore").decode("utf-8")
    name = name.lower().strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-z0-9_]+", "", name)
    return name

def find_image_for_conductor(conductor: str, images_dir: str):
    key = normalize_filename(conductor)
    if not key:
        return None
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = os.path.join(images_dir, f"{key}.{ext}")
        if os.path.exists(p):
            return p
    return None

def img_file_to_data_uri(path: str):
    """
    Convierte imagen local a data URI (base64) para que Streamlit la muestre sin file://
    """
    if not path or not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    mime = f"image/{ext}" if ext in {"png", "jpeg", "webp"} else "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

# =========================
# Styles
# =========================
st.markdown(
    """
<style>
/* KPIs */
.kpi-row { margin-top: 0.25rem; margin-bottom: 0.75rem; }

/* Card */
.card {
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 18px;
  padding: 14px;
  background: rgba(255,255,255,0.03);
  box-shadow: 0 10px 24px rgba(0,0,0,0.25);
}
.card h3 { margin: 10px 0 6px 0; font-size: 1.10rem; letter-spacing: 0.2px; }
.meta { color: rgba(255,255,255,0.78); font-size: 0.92rem; margin-bottom: 10px; line-height: 1.35; }
.divline { border-top: 1px solid rgba(255,255,255,0.09); margin: 10px 0; }

/* Badges */
.badge { display:inline-block; padding: 4px 10px; border-radius: 999px; font-size: 0.80rem; margin: 6px 6px 0 0; }
.badge-ok { background: rgba(0, 200, 120, 0.18); border: 1px solid rgba(0, 200, 120, 0.45); }
.badge-warn { background: rgba(255, 190, 0, 0.16); border: 1px solid rgba(255, 190, 0, 0.45); }
.badge-danger { background: rgba(255, 80, 80, 0.16); border: 1px solid rgba(255, 80, 80, 0.45); }
.badge-muted { background: rgba(160,160,160,0.12); border: 1px solid rgba(160,160,160,0.35); }

/* Imagen del vehículo (PNG recortado ok) */
.vehicle-img{
  width: 100%;
  height: 200px;
  object-fit: contain;
  background: linear-gradient(180deg, #0f1116 0%, #171a22 100%);
  border-radius: 14px;
  padding: 12px;
  border: 1px solid rgba(255,255,255,0.08);
}

/* Contenedor para overlay */
.img-wrap{
  position: relative;
  width: 100%;
}

/* Avatar circular del conductor */
.driver-avatar{
  position: absolute;
  left: 14px;
  bottom: -18px;
  width: 68px;
  height: 68px;
  border-radius: 9999px;
  object-fit: cover;
  background: rgba(15,17,22,0.95);
  border: 2px solid rgba(255,255,255,0.22);
  box-shadow: 0 10px 22px rgba(0,0,0,0.45);
}

/* para que el título no se “pegue” al avatar */
.title-spacer { margin-top: 18px; }

/* “Ficha” dentro del expander */
.kv {
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.02);
}
.kv p { margin: 6px 0; color: rgba(255,255,255,0.82); }
.kv strong { color: rgba(255,255,255,0.92); }

.small { font-size: 0.90rem; color: rgba(255,255,255,0.80); line-height: 1.4; }

/* Imagen grande dentro del expander */
.big-img{
  width: 100%;
  max-height: 520px;
  object-fit: contain;
  border-radius: 16px;
  background: rgba(15,17,22,0.95);
  border: 1px solid rgba(255,255,255,0.10);
  padding: 10px;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# Sidebar
# =========================
st.title("🚗 Flota: Cards, KPIs y Alertas")

with st.sidebar:
    st.header("Datos")
    excel_path = st.text_input("Ruta del Excel", value=EXCEL_PATH_DEFAULT)

    images_dir = st.text_input("Carpeta imágenes vehículo (por placas)", value=IMAGES_DIR_DEFAULT)
    images_conductor_dir = st.text_input("Carpeta imágenes conductor (por nombre)", value=IMAGES_CONDUCTOR_DIR_DEFAULT)

    vista = st.radio("Vista", ["🚗 Flota", "💸 Retorno de Inversión"], index=0)

    warn_days = st.slider("Alertar si vence en (días)", 7, 120, 30, 1)

    st.divider()
    st.header("Filtros")
    q = st.text_input("🔎 Buscar (placas, conductor, vehículo, socio, plataforma)")

    colA, colB = st.columns(2)
    with colA:
        only_verified = st.checkbox("Solo verificados", value=False)
        only_tenencia_ok = st.checkbox("Tenencia ✔", value=False)
    with colB:
        only_with_debt = st.checkbox("Con adeudo", value=False)
        only_expiring = st.checkbox("Solo por vencer/vencido", value=False)

# =========================
# Load
# =========================
try:
    df = load_data(excel_path, SHEET_NAME)
except Exception as e:
    st.error(f"No pude leer el archivo. Revisa ruta/hoja.\n\nDetalle: {e}")
    st.stop()

# =========================
# Vista selector
# =========================
if vista == "🚗 Flota":
    # =========================
    # Filters
    # =========================
    df_f = df.copy()
    if q.strip():

        q_raw = q.strip()


        # Campos permitidos para "campo:valor"

        field_aliases = {

            "placas": "PLACAS",

            "conductor": "CONDUCTOR",

            "vehiculo": "VEHICULO",

            "vehículo": "VEHICULO",

            "socio": "SOCIO",

            "plataforma": "PLATAFORMA",

            "detalle": "DETALLE",

        }


        # 1) Extraer tokens tipo campo:valor (permite comillas: socio:"Juan Perez")

        token_re = re.compile(r'(\w+):(?:"([^"]+)"|(\S+))', re.IGNORECASE)

        matches = list(token_re.finditer(q_raw))


        # AND entre cada campo:valor encontrado

        mask_field = True

        for m in matches:

            key = (m.group(1) or "").lower()

            val = (m.group(2) or m.group(3) or "").strip()


            col = field_aliases.get(key)

            if col and col in df_f.columns and val:

                pattern = re.escape(val)

                mask_field = mask_field & df_f[col].astype(str).str.contains(pattern, case=False, na=False)


        # 2) Quitar los tokens campo:valor del texto para que lo restante use el filtro normal

        q_rest = token_re.sub("", q_raw).strip()


        # 3) Filtro normal (tu comportamiento actual) para lo que quede

        mask_free = True

        if q_rest:

            pattern = re.escape(q_rest)

            fields = [c for c in ["PLACAS", "CONDUCTOR", "VEHICULO", "SOCIO", "PLATAFORMA", "DETALLE"] if c in df_f.columns]

            if fields:

                m_or = False

                for c in fields:

                    m_or = m_or | df_f[c].astype(str).str.contains(pattern, case=False, na=False)

                mask_free = m_or


        # 4) Aplicar ambos: (campo:valor) AND (búsqueda libre)

        df_f = df_f[mask_field & mask_free]

    if only_verified:
        df_f = df_f[df_f["FLAG_VERIFICADO"] == True]
    if only_tenencia_ok:
        df_f = df_f[df_f["FLAG_TENENCIA_OK"] == True]
    if only_with_debt:
        df_f = df_f[df_f["FLAG_ADEUDO"] == True]

    if only_expiring:
        def is_expiring(row):
            d1 = days_to(row.get("VIGENCIA_DT"))
            d2 = days_to(row.get("TCIRC_DT"))
            ok1 = (d1 is not None) and (d1 <= warn_days)
            ok2 = (d2 is not None) and (d2 <= warn_days)
            return ok1 or ok2
        df_f = df_f[df_f.apply(is_expiring, axis=1)]

    # =========================
    # KPIs
    # =========================
    total = int(df.shape[0])
    shown = int(df_f.shape[0])

    verificados = int(df["FLAG_VERIFICADO"].sum())
    tenencia_ok = int(df["FLAG_TENENCIA_OK"].sum())
    con_adeudo = int(df["FLAG_ADEUDO"].sum())

    def count_expiring(series_dt: pd.Series, warn_days: int) -> int:
        d = (series_dt.dt.date - date.today()).apply(lambda x: x.days if pd.notna(x) else None)
        return int(sum((x is not None) and (x <= warn_days) for x in d))

    poliza_exp = count_expiring(df["VIGENCIA_DT"], warn_days)
    tcirc_exp = count_expiring(df["TCIRC_DT"], warn_days)

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total vehículos", f"{total}")
    k2.metric("Mostrando", f"{shown}")
    k3.metric("Verificados", f"{verificados}")
    k4.metric("Tenencia ✔", f"{tenencia_ok}")
    k5.metric("Con adeudo", f"{con_adeudo}")
    k6.metric(f"Vence ≤ {warn_days}d", f"{poliza_exp + tcirc_exp}")

    st.markdown("<div class='kpi-row'></div>", unsafe_allow_html=True)

    # =========================
    # Order by urgency
    # =========================
    def urgency_score(row) -> int:
        d1 = days_to(row.get("VIGENCIA_DT"))
        d2 = days_to(row.get("TCIRC_DT"))
        vals = [v for v in [d1, d2] if v is not None]
        if not vals:
            return 10_000
        return min(vals)

    df_f = df_f.copy()
    df_f["__urg"] = df_f.apply(urgency_score, axis=1)
    df_f = df_f.sort_values(["__urg", "VEHICULO", "PLACAS"], ascending=[True, True, True])

    # =========================
    # Cards
    # =========================
    cols_per_row = 3
    rows = (len(df_f) + cols_per_row - 1) // cols_per_row

    def fmt_date(ts):
        if pd.isna(ts):
            return ""
        return ts.strftime("%Y-%m-%d")

    def fmt_money(x, symbol="$"):
        if pd.isna(x) or x == "":
            return ""
        try:
            return f"{symbol}{int(float(x)):,}"
        except Exception:
            return safe_str(x)

    for r in range(rows):
        cols = st.columns(cols_per_row)
        for i in range(cols_per_row):
            idx = r * cols_per_row + i
            if idx >= len(df_f):
                break

            row = df_f.iloc[idx]
            veh = safe_str(row.get("VEHICULO"))
            modelo = safe_str(row.get("MODELO"))
            placas = safe_str(row.get("PLACAS"))
            conductor = safe_str(row.get("CONDUCTOR"))
            plataforma = safe_str(row.get("PLATAFORMA"))
            socio = safe_str(row.get("SOCIO"))
            adeudo = fmt_money(row.get("ADEUDO"))
            poliza = safe_str(row.get("PÓLIZA"))

            d_vig = days_to(row.get("VIGENCIA_DT"))
            d_tc = days_to(row.get("TCIRC_DT"))

            b1_txt, b1_cls = alert_label(d_vig, warn_days)
            b2_txt, b2_cls = alert_label(d_tc, warn_days)

            verif = "✅" if bool(row.get("FLAG_VERIFICADO")) else "⚠️"
            ten_ok = "✅" if bool(row.get("FLAG_TENENCIA_OK")) else "⚠️"
            debt = "⚠️" if bool(row.get("FLAG_ADEUDO")) else "✅"

            # Imagen vehículo (por placas)
            img_path = find_image_for_plate(placas, images_dir)
            img_uri = img_file_to_data_uri(img_path) if img_path else None

            # Imagen conductor (por nombre normalizado)
            conductor_img_path = find_image_for_conductor(conductor, images_conductor_dir)
            conductor_img_uri = img_file_to_data_uri(conductor_img_path) if conductor_img_path else None

            with cols[i]:
                st.markdown("<div class='card'>", unsafe_allow_html=True)

                # === Bloque imagen + avatar circular ===
                st.markdown("<div class='img-wrap'>", unsafe_allow_html=True)

                if img_uri:
                    st.markdown(f"<img src='{img_uri}' class='vehicle-img'/>", unsafe_allow_html=True)
                else:
                    st.markdown(
                        "<img src='https://via.placeholder.com/1200x700.png?text=Sin+imagen' class='vehicle-img'/>",
                        unsafe_allow_html=True
                    )

                if conductor_img_uri:
                    st.markdown(
                        f"<img src='{conductor_img_uri}' class='driver-avatar' title='{conductor}'/>",
                        unsafe_allow_html=True
                    )

                st.markdown("</div>", unsafe_allow_html=True)  # img-wrap

                st.markdown(f"<h3 class='title-spacer'>{veh} {modelo} — {placas}</h3>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='meta'>"
                    f"Conductor: <b>{conductor or '—'}</b><br/>"
                    f"Plataforma: {plataforma or '—'} · Socio: {socio or '—'}"
                    f"</div>",
                    unsafe_allow_html=True
                )

                st.markdown(
                    f"""
                    <span class="badge {b1_cls}">Póliza: {b1_txt}</span>
                    <span class="badge {b2_cls}">T. circ.: {b2_txt}</span>
                    """,
                    unsafe_allow_html=True
                )

                st.markdown("<div class='divline'></div>", unsafe_allow_html=True)

                st.markdown(
                    f"""
                    <div class="small">
                    Verificación: {verif} &nbsp; | &nbsp;
                    Tenencia: {ten_ok} &nbsp; | &nbsp;
                    Adeudo: {debt} ({adeudo or "—"})
                    <br/>
                    Póliza: {poliza or "—"}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # ================
                # Ver imagen en grande (vehículo + conductor)
                # ================
                with st.expander("🖼️ Ver imagen"):
                    if img_uri:
                        st.markdown(f"**Vehículo ({placas})**", unsafe_allow_html=True)
                        st.markdown(f"<img src='{img_uri}' class='big-img'/>", unsafe_allow_html=True)
                    else:
                        st.info("No hay imagen del vehículo para esta unidad.")

                    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

                    if conductor_img_uri:
                        st.markdown(f"**Conductor ({conductor})**", unsafe_allow_html=True)
                        st.markdown(f"<img src='{conductor_img_uri}' class='big-img'/>", unsafe_allow_html=True)
                    else:
                        st.info("No hay imagen del conductor para esta unidad.")

                # ================
                # Ver más: FICHA TÉCNICA
                # ================
                with st.expander("Ver más"):
                    data = {
                        "Detalle": safe_str(row.get("DETALLE")),
                        "No. Serie": safe_str(row.get("# SERIE")),
                        "IMEI": safe_str(row.get("IMEI")),
                        "GPS": safe_str(row.get("# GPS")),
                        "Fecha compra": fmt_date(row.get("FECHA_COMPRA_DT")),
                        "Importe compra": fmt_money(row.get("IMPORTE_COMPRA_NUM")),
                        "Cuenta": fmt_money(row.get("CUENTA")),
                        "Tag": safe_str(row.get("TAG")),
                        "Observaciones": safe_str(row.get("OBSERVACIONES")),
                        "Vigencia póliza": fmt_date(row.get("VIGENCIA_DT")),
                        "Vigencia tarjeta circ.": fmt_date(row.get("TCIRC_DT")),
                    }

                    c1, c2 = st.columns(2)

                    def print_kv(container, title, keys):
                        container.markdown(f"**{title}**")
                        container.markdown("<div class='kv'>", unsafe_allow_html=True)
                        for k in keys:
                            v = data.get(k, "")
                            if v:
                                container.markdown(f"<p><strong>{k}:</strong> {v}</p>", unsafe_allow_html=True)
                        container.markdown("</div>", unsafe_allow_html=True)

                    print_kv(c1, "📌 Información", ["Detalle", "Fecha compra", "Importe compra", "Cuenta", "Tag"])
                    print_kv(c2, "🧾 Identificadores y vigencias", ["No. Serie", "IMEI", "GPS", "Vigencia póliza", "Vigencia tarjeta circ.", "Observaciones"])

                st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("📋 Ver tabla filtrada"):
        st.dataframe(df_f.drop(columns=["__urg"], errors="ignore"), use_container_width=True)

else:
    st.title("💸 Retorno de Inversión")

    if "DETALLE" not in df.columns:
        st.error("No encontré la columna 'DETALLE' en el Excel. Agrega/llena la columna DETALLE (ej: MODELO|AÑO|COLOR|PLACAS).")
        st.stop()

    q_det = st.text_input("🔎 Buscar unidad (ej. AVEO, VENTO, placas…)", "").strip()
    df_det = df.copy()
    if q_det:
        df_det = df_det[df_det["DETALLE"].astype(str).str.contains(re.escape(q_det), case=False, na=False)]

    detalles = sorted(df_det["DETALLE"].dropna().astype(str).unique())
    if not detalles:
        st.warning("No hay unidades que coincidan con tu búsqueda.")
        st.stop()

    detalle_sel = st.selectbox("Selecciona unidad (DETALLE)", detalles)

    row = df[df["DETALLE"].astype(str) == str(detalle_sel)].iloc[0]

    importe = float(row.get("IMPORTE_COMPRA_NUM")) if pd.notna(row.get("IMPORTE_COMPRA_NUM")) else 0.0
    cuenta = float(row.get("CUENTA_NUM")) if pd.notna(row.get("CUENTA_NUM")) else 0.0

    fecha_compra = row.get("FECHA_COMPRA_DT")
    if pd.isna(fecha_compra):
        st.warning("Este vehículo no tiene FECHA COMPRA válida; usaré la fecha de hoy.")
        fecha_compra = pd.Timestamp.today().normalize()
    else:
        fecha_compra = pd.to_datetime(fecha_compra).normalize()

    primer_lunes = fecha_compra + pd.Timedelta(days=(0 - fecha_compra.weekday()) % 7)

    c1, c2, c3 = st.columns(3)
    with c1:
        pago_semanal = st.number_input("Pago semanal ($)", min_value=0.0, value=float(cuenta) if cuenta > 0 else 0.0, step=500.0)
    with c2:
        enganche = st.number_input("Enganche inicial ($)", min_value=0.0, value=0.0, step=1000.0)
    with c3:
        st.write("**Pagos cada lunes desde:**")
        st.write(primer_lunes.strftime("%d/%m/%Y"))

    if importe <= 0:
        st.error("Este vehículo no tiene un IMPORTE COMPRA válido.")
        st.stop()
    if pago_semanal <= 0:
        st.error("La CUENTA / pago semanal debe ser mayor a 0 para simular el payback.")
        st.stop()

    saldo_inicial = max(0.0, importe - enganche)

    rows = []
    saldo = saldo_inicial
    acumulado = enganche
    semana = 1
    fecha_pago = primer_lunes

    while saldo > 0 and semana <= 520:
        pago = min(pago_semanal, saldo)
        acumulado += pago
        saldo -= pago

        rows.append({
            "SEMANA": semana,
            "FECHA_PAGO": fecha_pago,
            "PAGO": pago,
            "ACUMULADO": acumulado,
            "SALDO": saldo
        })

        fecha_pago += pd.Timedelta(days=7)
        semana += 1

    df_pay = pd.DataFrame(rows)
    semanas_total = int(df_pay["SEMANA"].max()) if not df_pay.empty else 0
    anios_aprox = semanas_total / 52

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Importe compra", f"${importe:,.0f}")
    k2.metric("Enganche", f"${enganche:,.0f}")
    k3.metric("Saldo a recuperar", f"${saldo_inicial:,.0f}")
    k4.metric("Payback", f"{semanas_total} semanas")
    k5.metric("Equivalente", f"{anios_aprox:.2f} años")

    st.divider()

    st.subheader("📅 Desglose semanal (pagos en lunes)")
    st.dataframe(df_pay, use_container_width=True)

    if not df_pay.empty:
        df_pay["FECHA_PAGO"] = pd.to_datetime(df_pay["FECHA_PAGO"])
        df_pay["MES"] = df_pay["FECHA_PAGO"].dt.to_period("M").astype(str)
        df_pay["AÑO"] = df_pay["FECHA_PAGO"].dt.to_period("Y").astype(str)

        st.subheader("📆 Resumen mensual")
        df_m = df_pay.groupby("MES", as_index=False).agg(
            PAGO_TOTAL=("PAGO","sum"),
            ACUMULADO_FINAL=("ACUMULADO","max"),
            SALDO_FINAL=("SALDO","min")
        )
        st.dataframe(df_m, use_container_width=True)

        st.subheader("📆 Resumen anual")
        df_y = df_pay.groupby("AÑO", as_index=False).agg(
            PAGO_TOTAL=("PAGO","sum"),
            ACUMULADO_FINAL=("ACUMULADO","max"),
            SALDO_FINAL=("SALDO","min")
        )
        st.dataframe(df_y, use_container_width=True)