"""
Página pública de disponibilidad rápida — acceso sin login.
Protegida con token en la URL: ?token=TUTOKEN

Uso desde celular:
  https://tuapp.streamlit.app/disponibilidad_rapida?token=TUTOKEN
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Agregar raíz del proyecto al path ──
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db import Database
from core.repositories import DisponibilidadRepo

# ─────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────
ACCESS_TOKEN = "hospedaje2024"          # ← cambiá este token si querés más seguridad
DB_PATH      = ROOT / "data" / "hospedaje.db"

st.set_page_config(
    page_title="Disponibilidad",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────
#  VALIDAR TOKEN
# ─────────────────────────────────────────────────────────
params = st.query_params
token  = params.get("token", "")

if token != ACCESS_TOKEN:
    st.markdown("""
        <style>
            [data-testid="stSidebarNav"] { display: none; }
        </style>
    """, unsafe_allow_html=True)
    st.error("🔒 Acceso no autorizado. Usá el link completo con token.")
    st.stop()

# Ocultar sidebar y navegación de páginas en móvil
st.markdown("""
    <style>
        [data-testid="stSidebarNav"] { display: none; }
        [data-testid="stSidebar"]    { display: none; }
        .block-container { padding-top: 1rem; padding-bottom: 1rem; }
        /* Texto más grande en móvil */
        @media (max-width: 768px) {
            td, th { font-size: 14px !important; }
        }
    </style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
#  INICIALIZAR BD
# ─────────────────────────────────────────────────────────
db = Database(db_path=DB_PATH, project_root=ROOT)
db.ensure_database()

# ─────────────────────────────────────────────────────────
#  HELPERS DE COLOR
# ─────────────────────────────────────────────────────────
def _color_estado(val: str):
    if val == "Ocupado":
        return "background-color: #ffcccc; color: #cc0000; font-weight: 700;"
    if val == "Dueño":
        return "background-color: #ffe5b4; color: #cc6600; font-weight: 700;"
    if val == "Libre":
        return "background-color: #ccffcc; color: #006600; font-weight: 700;"
    if val == "—":
        return "color: #aaaaaa;"
    return ""

def _dia_corto(d: date) -> str:
    dias  = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
    meses = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
    return f"{dias[d.weekday()]} {d.day}-{meses[d.month-1]}"

def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())

def _domingo(d: date) -> date:
    return _lunes(d) + timedelta(days=6)

# ─────────────────────────────────────────────────────────
#  HEADER
# ─────────────────────────────────────────────────────────
st.markdown("## 🏠 Disponibilidad de departamentos")

# Leyenda de colores compacta
st.markdown(
    '<span style="color:#006600;font-weight:700">■ Libre</span> &nbsp;&nbsp;'
    '<span style="color:#cc0000;font-weight:700">■ Ocupado</span> &nbsp;&nbsp;'
    '<span style="color:#cc6600;font-weight:700">■ Dueño</span>',
    unsafe_allow_html=True
)

st.markdown("---")

# ─────────────────────────────────────────────────────────
#  FILTROS — compactos para móvil
# ─────────────────────────────────────────────────────────
usuario = "movil"   # filtros persistidos separados del login normal

# Leer preferencias guardadas
try:
    f_ini_raw = db.get_preferencia(usuario, "disp_rapida_f_ini")
    f_ini_def = date.fromisoformat(f_ini_raw) if f_ini_raw else date.today()
except Exception:
    f_ini_def = date.today()

try:
    f_fin_raw = db.get_preferencia(usuario, "disp_rapida_f_fin")
    f_fin_def = date.fromisoformat(f_fin_raw) if f_fin_raw else date.today() + timedelta(days=14)
except Exception:
    f_fin_def = date.today() + timedelta(days=14)

# Departamentos
deps = db.fetch_df("SELECT codigo, numero FROM departamentos ORDER BY numero;")
opciones = [f"{row['numero']} (cod {int(row['codigo'])})" for _, row in deps.iterrows()]

try:
    sel_raw = db.get_preferencia(usuario, "disp_rapida_sel")
    sel_def = json.loads(sel_raw) if sel_raw else opciones
    sel_def = [s for s in sel_def if s in opciones]
    if not sel_def:
        sel_def = opciones
except Exception:
    sel_def = opciones

# Inputs en una sola fila
c1, c2 = st.columns(2)
with c1:
    f_ini = st.date_input("Desde", value=f_ini_def, key="dr_ini")
with c2:
    f_fin = st.date_input("Hasta", value=f_fin_def, key="dr_fin")

with st.expander("🔍 Filtrar departamentos", expanded=False):
    sel = st.multiselect("Departamentos", opciones, default=sel_def, key="dr_sel")
    if not sel:
        sel = opciones

# Guardar preferencias
try:
    db.set_preferencia(usuario, "disp_rapida_f_ini", f_ini.isoformat())
    db.set_preferencia(usuario, "disp_rapida_f_fin", f_fin.isoformat())
    db.set_preferencia(usuario, "disp_rapida_sel",   json.dumps(sel))
except Exception:
    pass

if f_ini > f_fin:
    st.warning("La fecha Desde no puede ser mayor que Hasta.")
    st.stop()

codigos = [int(item.split("cod")[-1].strip(" )")) for item in sel] if sel else None

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
    .sort_values(
        by="departamento",
        key=lambda s: s.astype(str).str.extract(r"(\d+)").astype(float).fillna(0).iloc[:, 0]
    )["departamento"].tolist()
)

# ─────────────────────────────────────────────────────────
#  RESUMEN RÁPIDO  (métricas útiles en móvil)
# ─────────────────────────────────────────────────────────
total_dias   = len(df["fecha"].unique())
libres       = int((df["ocupado"] == 0).sum())
ocupados     = int((df["ocupado"] == 1).sum())
bloqueados   = int((df["ocupado"] == 2).sum())
pct_libre    = round(libres / max(len(df), 1) * 100)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Días del período", total_dias)
c2.metric("🟢 Libre",  f"{pct_libre}%")
c3.metric("🔴 Ocupado", ocupados)
c4.metric("🟠 Dueño",   bloqueados)

st.markdown("---")

# ─────────────────────────────────────────────────────────
#  CALENDARIO SEMANAL
# ─────────────────────────────────────────────────────────
actual  = _lunes(f_ini)
semanas = []
while actual <= f_fin:
    semanas.append((actual, _domingo(actual)))
    actual = _domingo(actual) + timedelta(days=1)

for w_ini, w_fin in semanas:
    fechas = [w_ini + timedelta(days=k) for k in range(7)]
    cols   = [_dia_corto(d) for d in fechas]

    data = {"Depto": departamentos}
    for d, col in zip(fechas, cols):
        if d < f_ini or d > f_fin:
            data[col] = ["—"] * len(departamentos)
        else:
            mapa = df[df["fecha"] == d.isoformat()].set_index("departamento")["estado"].to_dict()
            data[col] = [mapa.get(dep, "Libre") for dep in departamentos]

    df_sem = pd.DataFrame(data)

    label = f"**{w_ini.strftime('%d %b')} → {w_fin.strftime('%d %b %Y')}**"
    st.markdown(label)

    try:
        styled = df_sem.style.map(_color_estado, subset=cols)
    except AttributeError:
        styled = df_sem.style.applymap(_color_estado, subset=cols)

    st.dataframe(styled, use_container_width=True, hide_index=True, height=None)

# ─────────────────────────────────────────────────────────
#  FOOTER con fecha de actualización
# ─────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Actualizado: {date.today().strftime('%d/%m/%Y')} · 🏠 Gestión Hospedaje Gonzalo Estrella")
