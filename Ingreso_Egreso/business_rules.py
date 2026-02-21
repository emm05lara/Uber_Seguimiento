# business_rules.py
# ──────────────────────────────────────────────────────────────
# Módulo de reglas de negocio — Operación UBER 2025 / 2026
# Lee prueba.xlsx (4 hojas) y expone DataFrames limpios.
# ──────────────────────────────────────────────────────────────
from __future__ import annotations

import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE HOJAS
# ═══════════════════════════════════════════════════════════════
SHEETS = {
    "ingresos": {
        2025: {"name": "UBER 2025", "header_row": 1},
        2026: {"name": "UBER 2026", "header_row": 0},
    },
    "egresos": {
        2025: {"name": "Gastos 2025", "header_row": 0},
        2026: {"name": "Gastos 2026", "header_row": 0},
    },
}

# ═══════════════════════════════════════════════════════════════
# MAPEO DE COLUMNAS — INGRESOS  (UBER 2025 / 2026)
# ═══════════════════════════════════════════════════════════════
# Nombres canónicos → nombres reales por año
_INGRESOS_RENAME = {
    2025: {
        "SEM": "semana",
        "CONDUCTOR": "conductor",
        "AUTO": "llave",               # en 2025 se llama AUTO
        "TAG": "tag",
        "SOCIO": "socio",
        "PLATAFORMA": "plataforma",
        "APP": "app",
        "GANANCIA": "ganancia",
        "RENTA": "renta_raw",
        "SEM PASADA": "sem_pasada",
        "FIANZA": "fianza_raw",
        "MULTA": "multa_raw",
        "HOJALATERO": "hojalatero_raw",
        "DESCUENTOS": "descuentos_raw",
        "TOTAL": "total",
        "GANANCIAS TOTALES": "ganancias_totales",
        "COMENTARIOS": "comentarios",
    },
    2026: {
        "SEM": "semana",
        "CONDUCTOR": "conductor",
        "LLAVE": "llave",               # en 2026 se llama LLAVE
        "TAG": "tag",
        "SOCIO": "socio",
        "PLATAFORMA": "plataforma",
        "APP": "app",
        "GANANCIA": "ganancia",
        "RENTA": "renta_raw",
        "SEM PASADA": "sem_pasada",
        "FIANZA": "fianza_raw",
        "MULTA": "multa_raw",
        "HOJALATERO": "hojalatero_raw",
        "DESCUENTOS": "descuentos_raw",
        "TOTAL": "total",
        "GANANCIAS \nTOTALES": "ganancias_totales",   # nombre real con salto
        "COMENTARIOS": "comentarios",
    },
}

# ═══════════════════════════════════════════════════════════════
# MAPEO DE COLUMNAS — EGRESOS  (Gastos 2025 / 2026)
# ═══════════════════════════════════════════════════════════════
_EGRESOS_RENAME = {
    2025: {
        "Semana": "semana",
        "MES": "mes",
        "Fecha": "fecha",
        "Solicitante": "solicitante",
        "CONCEPTO": "concepto",
        "DETALLE": "detalle",
        "CONDUCTOR": "conductor",
        "DETALLE.1": "llave",            # 2025 usa segunda col DETALLE como llave
        "SOCIO": "socio",
        "METODO DE PAGO": "metodo_pago",
        "REAL": "monto_real",
        "COMERCIO": "comercio",
        "COMENTARIOS": "comentarios",
        "ADICIONAL": "adicional",
    },
    2026: {
        "SEMANA": "semana",
        "MES": "mes",
        "FECHA": "fecha",
        "CONCEPTO": "concepto",
        "DETALLE": "detalle",
        "CONDUCTOR": "conductor",
        "LLAVE": "llave",
        "SOCIO": "socio",
        "METODO DE PAGO": "metodo_pago",
        "RESPONSABLE": "responsable",
        "REAL": "monto_real",
        "COMERCIO": "comercio",
        "COMENTARIOS": "comentarios",
        "ADICIONAL": "adicional",
        "FOLIO FISCAL": "folio_fiscal",
    },
}

# Columnas numéricas que siempre se convierten
_INGRESOS_NUMERIC = [
    "ganancia", "renta_raw", "sem_pasada", "fianza_raw",
    "multa_raw", "hojalatero_raw", "descuentos_raw",
    "total", "ganancias_totales",
]

_EGRESOS_NUMERIC = ["monto_real"]


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def _coerce_numeric(s: pd.Series) -> pd.Series:
    """Convierte a numérico aceptando $, comas, paréntesis (negativos)."""
    if s is None or pd.api.types.is_numeric_dtype(s):
        return s
    x = s.astype(str).str.strip()
    x = x.replace({"nan": np.nan, "None": np.nan, "": np.nan, "-": np.nan})
    x = x.str.replace(r"^\((.+)\)$", r"-\1", regex=True)
    x = x.str.replace(r"[^0-9,.\-]", "", regex=True)

    def _fix_commas(val):
        if pd.isna(val):
            return val
        val = str(val)
        if "," not in val:
            return val
        if "." in val:
            return val.replace(",", "")
        return val.replace(",", ".")

    x = x.apply(_fix_commas)
    return pd.to_numeric(x, errors="coerce")


def _strip_unnamed(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed")]


# ═══════════════════════════════════════════════════════════════
# TRANSFORMACIONES — INGRESOS
# ═══════════════════════════════════════════════════════════════
def _invertir_signo_fianza(val):
    """Regla: en el Excel '-' representa ingreso de dinero,
    '+' es devolución al conductor.  Invertimos para que
    positivo = ingreso, negativo = devolución."""
    if pd.isna(val):
        return 0.0
    return float(val) * -1


def generar_concepto_ingreso(row: pd.Series) -> str:
    """Genera etiqueta de concepto según qué columnas tienen valor."""
    partes = []
    if abs(row.get("renta_semanal", 0) or 0) > 0:
        partes.append("Renta")
    if (row.get("fianza", 0) or 0) != 0:
        partes.append("Fianza")
    if abs(row.get("multa", 0) or 0) > 0:
        partes.append("Multa")
    if abs(row.get("hojalatero", 0) or 0) > 0:
        partes.append("Hojalatero")
    if abs(row.get("descuentos", 0) or 0) > 0:
        partes.append("Descuento")
    return " + ".join(partes) if partes else "Sin concepto"


def transform_ingresos(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica reglas de negocio a un DataFrame de ingresos ya renombrado."""
    out = df.copy()

    # Valor absoluto: renta, multa, hojalatero, descuentos
    out["renta_semanal"] = out["renta_raw"].fillna(0).abs()
    out["multa"]         = out["multa_raw"].fillna(0).abs()
    out["hojalatero"]    = out["hojalatero_raw"].fillna(0).abs()
    out["descuentos"]    = out["descuentos_raw"].fillna(0).abs()

    # Fianza: invertir signo
    out["fianza"] = out["fianza_raw"].apply(_invertir_signo_fianza)

    # Concepto auto-generado
    out["concepto_ingreso"] = out.apply(generar_concepto_ingreso, axis=1)

    # Limpiar columnas raw
    out.drop(columns=[
        "renta_raw", "multa_raw", "hojalatero_raw",
        "descuentos_raw", "fianza_raw",
    ], inplace=True)

    return out


# ═══════════════════════════════════════════════════════════════
# TRANSFORMACIONES — EGRESOS
# ═══════════════════════════════════════════════════════════════
def transform_egresos(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica reglas de negocio a un DataFrame de egresos ya renombrado."""
    out = df.copy()
    out["monto_real"] = out["monto_real"].fillna(0).abs()
    return out


# ═══════════════════════════════════════════════════════════════
# CARGA PRINCIPAL
# ═══════════════════════════════════════════════════════════════
def load_ingresos(
    path: str = "prueba.xlsx",
    años: list[int] | None = None,
) -> pd.DataFrame:
    """Lee hojas UBER 2025 / 2026 y devuelve DataFrame unificado y transformado."""
    if años is None:
        años = [2025, 2026]

    frames = []
    for año in años:
        cfg = SHEETS["ingresos"].get(año)
        if cfg is None:
            continue
        try:
            raw = pd.read_excel(path, sheet_name=cfg["name"], header=cfg["header_row"])
        except Exception:
            continue

        raw = _strip_unnamed(raw)
        raw.columns = [str(c).strip() for c in raw.columns]

        rename = _INGRESOS_RENAME.get(año, {})
        # Solo renombrar columnas que existen
        rename_valid = {k: v for k, v in rename.items() if k in raw.columns}
        df = raw.rename(columns=rename_valid)

        # Coerción numérica
        for col in _INGRESOS_NUMERIC:
            if col in df.columns:
                df[col] = _coerce_numeric(df[col])

        df["semana"] = pd.to_numeric(df.get("semana"), errors="coerce").astype("Int64")
        df["año"] = año

        # Filtrar filas sin semana (encabezados, totales)
        df = df.dropna(subset=["semana"])

        frames.append(df)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    return transform_ingresos(combined)


def load_egresos(
    path: str = "prueba.xlsx",
    años: list[int] | None = None,
) -> pd.DataFrame:
    """Lee hojas Gastos 2025 / 2026 y devuelve DataFrame unificado y transformado."""
    if años is None:
        años = [2025, 2026]

    frames = []
    for año in años:
        cfg = SHEETS["egresos"].get(año)
        if cfg is None:
            continue
        try:
            raw = pd.read_excel(path, sheet_name=cfg["name"], header=cfg["header_row"])
        except Exception:
            continue

        raw = _strip_unnamed(raw)
        raw.columns = [str(c).strip() for c in raw.columns]

        rename = _EGRESOS_RENAME.get(año, {})
        rename_valid = {k: v for k, v in rename.items() if k in raw.columns}
        df = raw.rename(columns=rename_valid)

        for col in _EGRESOS_NUMERIC:
            if col in df.columns:
                df[col] = _coerce_numeric(df[col])

        df["semana"] = pd.to_numeric(df.get("semana"), errors="coerce").astype("Int64")
        df["año"] = año

        df = df.dropna(subset=["semana"])

        frames.append(df)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    return transform_egresos(combined)


# ═══════════════════════════════════════════════════════════════
# UTILIDADES PARA DASHBOARD
# ═══════════════════════════════════════════════════════════════
def yearweek_key(año, semana) -> int:
    """Crea un entero AÑO*100 + SEM para ordenar."""
    return int(año) * 100 + int(semana)


def yearweek_label(key: int) -> str:
    y = key // 100
    w = key % 100
    return f"{y}-S{w:02d}"


def add_yearweek(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega columnas YEARWEEK y WEEK_LABEL para agrupar por semana."""
    out = df.copy()
    out["YEARWEEK"] = out["año"].astype("Int64") * 100 + out["semana"].astype("Int64")
    out["WEEK_LABEL"] = out["YEARWEEK"].dropna().astype(int).map(yearweek_label)
    return out


# ═══════════════════════════════════════════════════════════════
# EJECUCIÓN DIRECTA (prueba rápida)
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("Cargando prueba.xlsx ...")
    print("=" * 60)

    df_ing = load_ingresos()
    print(f"\n✅ Ingresos: {len(df_ing)} filas")
    print(f"   Columnas: {list(df_ing.columns)}")
    print(f"   Años: {sorted(df_ing['año'].unique())}")
    if len(df_ing) > 0:
        print(f"   Renta semanal (ejemplo): {df_ing['renta_semanal'].head(3).tolist()}")
        print(f"   Fianza (ejemplo):        {df_ing['fianza'].head(3).tolist()}")
        print(f"   Conceptos:               {df_ing['concepto_ingreso'].value_counts().head(5).to_dict()}")
        print(f"   Ganancias totales sum:    ${df_ing['ganancias_totales'].sum():,.2f}")

    df_egr = load_egresos()
    print(f"\n✅ Egresos: {len(df_egr)} filas")
    print(f"   Columnas: {list(df_egr.columns)}")
    print(f"   Años: {sorted(df_egr['año'].unique())}")
    if len(df_egr) > 0:
        print(f"   Monto real (ejemplo):     {df_egr['monto_real'].head(3).tolist()}")
        print(f"   Gasto total sum:          ${df_egr['monto_real'].sum():,.2f}")
        if "concepto" in df_egr.columns:
            print(f"   Top conceptos:            {df_egr['concepto'].value_counts().head(5).to_dict()}")

    print("\n✅ Módulo business_rules.py OK")
