"""
Página pública de disponibilidad rápida — acceso sin login.
URL: https://hospedaje-app-gget79.streamlit.app/disponibilidad_rapida?token=hospedaje2024
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Path: subir un nivel desde pages/ hasta la raíz del proyecto ──
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db import Database
from core.repositories import DisponibilidadRepo

# ─────────────────────────────────────────────────────────
#  CONFIG  (debe ser la primera llamada st.*)
# ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Disponibilidad 🏠",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

ACCESS_TOKEN = "hospedaje2024"

# Ocultar navegación de páginas y sidebar
st.markdown("""
    <style>
        [data-testid="stSidebarNav"],
        [data-testid="stSidebar"] { display: none !important; }
        .block-container { padding-top: 1rem !important; }
        @media (max-width: 768px) {
            td, th { font-size: 13px !important; }
        }
    </style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
#  VALIDAR TOKEN
# ─────────────────────────────────────────────────────────
token = st.query_params.get("token", "")

if token != ACCESS_TOKEN:
    st.error("🔒 Acceso no autorizado.")
    st.caption("Usá el link completo con el token de acceso.")
    st.stop()

# ─────────────────────────────────────────────────────────
#  BASE DE DATOS  — buscar hospedaje.db en varias rutas
# ─────────────────────────────────────────────────────────
def _find_db() -> Path:
    candidatos = [
        ROOT / "data" / "hospedaje.db",
        ROOT / "hospedaje-app" / "data" / "hospedaje.db",
        Path("/mnt/data/database.db"),                      # Railway
    ]
    for c in candidatos:
        if c.exists():
            return c
    # Si no existe, devolverla igual (se creará vacía)
    return ROOT / "data" / "hospedaje.db"

DB_PATH = _find_db()

try:
    db = Database(db_path=DB_PATH, project_root=ROOT)
    db.ensure_database()
except Exception as e:
    st.error(f"Error al conectar con la base de datos: {e}")
    st.stop()

# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────
def _color(val: str):
    if val == "Ocupado":
        return "background-color:#ffcccc;color:#cc0000;font-weight:700;"
    if val == "Dueño":
        return "background-color:#ffe5b4;color:#cc6600;font-weight:700;"
    if val == "Libre":
        return "background-color:#ccffcc;color:#006600;font-weight:700;"
    if val == "—":
        return "color:#bbbbbb;"
    return ""

def _dia(d: date) -> str:
    dias  = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
    meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
    return f"{dias[d.weekday()]} {d.day}/{meses[d.month-1]}"

def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())

# ─────────────────────────────────────────────────────────
#  HEADER
# ─────────────────────────────────────────────────────────
st.markdown("## 🏠 Disponibilidad de departamentos")
st.markdown(
    '<span style="color:#006600;font-weight:700">■ Libre</span>&nbsp;&nbsp;'
    '<span style="color:#cc0000;font-weight:700">■ Ocupado</span>&nbsp;&nbsp;'
    '<span style="color:#cc6600;font-weight:700">■ Dueño</span>',
    unsafe_allow_html=True
)
st.markdown("---")

# ─────────────────────────────────────────────────────────
#  FILTROS con persistencia en BD
# ─────────────────────────────────────────────────────────
usuario = "movil"

try:
    raw = db.get_preferencia(usuario, "dr_f_ini")
    f_ini_def = date.fromisoformat(raw) if raw else date.today()
except Exception:
    f_ini_def = date.today()

try:
    raw = db.get_preferencia(usuario, "dr_f_fin")
    f_fin_def = date.fromisoformat(raw) if raw else date.today() + timedelta(days=14)
except Exception:
    f_fin_def = date.today() + timedelta(days=14)

deps    = db.fetch_df("SELECT codigo, numero FROM departamentos ORDER BY numero;")
if deps.empty:
    st.info("No hay departamentos registrados aún.")
    st.stop()

opciones = [f"{r['numero']} (cod {int(r['codigo'])})" for _, r in deps.iterrows()]

try:
    raw     = db.get_preferencia(usuario, "dr_sel")
    sel_def = json.loads(raw) if raw else opciones
    sel_def = [s for s in sel_def if s in opciones] or opciones
except Exception:
    sel_def = opciones

c1, c2 = st.columns(2)
with c1:
    f_ini = st.date_input("Desde", value=f_ini_def, key="dr_ini")
with c2:
    f_fin = st.date_input("Hasta", value=f_fin_def, key="dr_fin")

with st.expander("🔍 Filtrar departamentos", expanded=False):
    sel = st.multiselect("Departamentos", opciones, default=sel_def, key="dr_sel")
    if not sel:
        sel = opciones

# Guardar en BD
try:
    db.set_preferencia(usuario, "dr_f_ini", f_ini.isoformat())
    db.set_preferencia(usuario, "dr_f_fin", f_fin.isoformat())
    db.set_preferencia(usuario, "dr_sel",   json.dumps(sel))
except Exception:
    pass

if f_ini > f_fin:
    st.warning("La fecha Desde no puede ser mayor que Hasta.")
    st.stop()

codigos = [int(s.split("cod")[-1].strip(" )")) for s in sel] if sel else None

# ─────────────────────────────────────────────────────────
#  DATOS
# ─────────────────────────────────────────────────────────
repo = DisponibilidadRepo(db)
df   = repo.disponibilidad_por_rango(f_ini, f_fin, codigos=codigos)

if df.empty:
    st.info("Sin datos para el rango seleccionado.")
    st.stop()

df["estado"] = df["ocupado"].map(
    lambda x: "Dueño" if int(x) == 2 else ("Ocupado" if int(x) == 1 else "Libre")
)

departamentos = (
    df[["departamento"]].drop_duplicates()
    .sort_values("departamento",
        key=lambda s: s.astype(str).str.extract(r"(\d+)").astype(float).fillna(0).iloc[:,0])
    ["departamento"].tolist()
)

# ── Métricas rápidas ──
pct_libre  = round((df["ocupado"] == 0).sum() / max(len(df), 1) * 100)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Período (días)", len(df["fecha"].unique()))
c2.metric("🟢 Libre",   f"{pct_libre}%")
c3.metric("🔴 Ocupado", int((df["ocupado"] == 1).sum()))
c4.metric("🟠 Dueño",   int((df["ocupado"] == 2).sum()))
st.markdown("---")

# ── Calendario semanal ──
actual = _lunes(f_ini)
while actual <= f_fin:
    w_fin   = actual + timedelta(days=6)
    fechas  = [actual + timedelta(days=k) for k in range(7)]
    cols    = [_dia(d) for d in fechas]

    data = {"Depto": departamentos}
    for d, col in zip(fechas, cols):
        if d < f_ini or d > f_fin:
            data[col] = ["—"] * len(departamentos)
        else:
            mapa    = df[df["fecha"] == d.isoformat()].set_index("departamento")["estado"].to_dict()
            data[col] = [mapa.get(dep, "Libre") for dep in departamentos]

    st.markdown(f"**{actual.strftime('%d %b')} → {w_fin.strftime('%d %b %Y')}**")

    df_sem = pd.DataFrame(data)
    try:
        styled = df_sem.style.map(_color, subset=cols)
    except AttributeError:
        styled = df_sem.style.applymap(_color, subset=cols)

    st.dataframe(styled, use_container_width=True, hide_index=True)

    actual = w_fin + timedelta(days=1)

st.markdown("---")
st.caption(f"🏠 Hospedaje Gonzalo Estrella · {date.today().strftime('%d/%m/%Y')}")
