from __future__ import annotations
from datetime import date, datetime, timedelta

import locale

import pandas as pd
import streamlit as st

def filter_dataframe(df: pd.DataFrame, title: str = "Filtros"):
    """
    Crea filtros por columna para un DataFrame.
    - Numéricas: slider (si min < max), si min == max muestra un caption y no crea slider.
    - Fecha: par de date_input (desde/hasta).
    - Texto/otros: text_input 'contiene'.
    Devuelve el DataFrame filtrado.
    """
    with st.expander(title, expanded=False):
        dff = df.copy()

        for col in df.columns:
            col_series = df[col]

            # 1) NUMÉRICO (si es object pero convertible, intenta convertir)
            if pd.api.types.is_numeric_dtype(col_series) or (
                pd.api.types.is_object_dtype(col_series)
                and pd.to_numeric(col_series, errors="coerce").notna().any()
            ):
                if not pd.api.types.is_numeric_dtype(col_series):
                    # convierte copia sin romper df original
                    col_numeric = pd.to_numeric(col_series, errors="coerce")
                else:
                    col_numeric = col_series

                min_v = float(col_numeric.min(skipna=True)) if col_numeric.notna().any() else None
                max_v = float(col_numeric.max(skipna=True)) if col_numeric.notna().any() else None

                if min_v is None or max_v is None:
                    continue  # no hay datos filtrables

                if min_v < max_v:
                    vmin, vmax = st.slider(f"{col}", min_value=min_v, max_value=max_v, value=(min_v, max_v))
                    dff = dff[(pd.to_numeric(dff[col], errors="coerce") >= vmin) &
                              (pd.to_numeric(dff[col], errors="coerce") <= vmax)]
                else:
                    # Rango degenerado: todos los valores iguales
                    st.caption(f"{col}: {min_v} (sin rango para filtrar)")
                    # No filtramos; deja pasar todo

            # 2) FECHA / DATETIME
            elif pd.api.types.is_datetime64_any_dtype(col_series):
                # Usa límites del propio dataframe si quieres valores por defecto inteligentes
                dmin = pd.to_datetime(col_series, errors="coerce").min()
                dmax = pd.to_datetime(col_series, errors="coerce").max()
                c1, c2 = st.columns(2)
                with c1:
                    d1 = st.date_input(f"{col} desde", value=dmin.date() if pd.notna(dmin) else None)
                with c2:
                    d2 = st.date_input(f"{col} hasta", value=dmax.date() if pd.notna(dmax) else None)
                if d1 and d2:
                    s = pd.to_datetime(dff[col], errors="coerce")
                    dff = dff[(s.dt.date >= d1) & (s.dt.date <= d2)]

            # 3) TEXTO / CATEGÓRICOS
            else:
                txt = st.text_input(f"{col} contiene", "")
                if txt:
                    dff = dff[dff[col].astype(str).str.contains(txt, case=False, na=False)]

        return dff  # dentro del expander

    # Si el expander no se despliega, retorna el original
    return df

def iso(d) -> str:
    """Convierte date/datetime/str a ISO8601 (YYYY-MM-DD)."""
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d")
    return str(d)

def calcular_noches(ingreso: date, salida: date) -> int:
    try:
        return max((salida - ingreso).days, 0)
    except Exception:
        return 0

def moneda(v: float) -> str:
    try:
        return f"${v:,.2f}"
    except Exception:
        return str(v)

#get.sn

def date_range(fi: date, ff: date):
    """Genera fechas [fi, ff] inclusive."""
    d = fi
    while d <= ff:
        yield d
        d += timedelta(days=1)

def dia_corto_es(d: date) -> str:
    """Devuelve, por ejemplo: 'Lunes 23-feb'."""
    # Evita depender de locale del SO: map manual
    dias = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
    return f"{dias[d.weekday()]} {d.day}-{meses[d.month-1]}"

def estado_texto(ocupado: int) -> str:
    return "Ocupado" if ocupado else "Libre"

#get.en