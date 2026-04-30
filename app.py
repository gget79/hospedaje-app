from __future__ import annotations
from pathlib import Path
import streamlit as st

from core.db import Database
from core.repositories import (
    PerfilUsuariosRepo, UsuariosRepo, PropietariosRepo, DepartamentosRepo,
    ConceptoGastosRepo, GastosRepo, ReservasRepo
)

# Admin
from ui.admin import (
    ui_admin_base_datos, ui_admin_usuarios, ui_admin_limpiar_bd, ui_admin_limpiar_bd_2,
    ui_admin_saldo_inicial, ui_admin_importar_excel
)

# ⚠️ Importa el MÓDULO completo (robusto):
from ui import catalogos as cat

# Resto de vistas
from ui.reservas import ui_reservas
from ui.ingresos import ui_autorizacion_ingreso
from ui.reportes import ui_rep_reservas, ui_rep_gastos, ui_rep_diario, ui_rep_disponibilidad, ui_rep_reservas_saldo_pendiente


# --- Helpers de autenticación de Administrador ---
ADMIN_PASS = "12345678"
ADMIN_SESSION_KEY = "admin_ok"

def ensure_admin_state():
    if ADMIN_SESSION_KEY not in st.session_state:
        st.session_state[ADMIN_SESSION_KEY] = False

def is_admin_authenticated() -> bool:
    return bool(st.session_state.get(ADMIN_SESSION_KEY, False))

def admin_login_widget():
    ensure_admin_state()

    # Si se solicitó limpiar en el run anterior, hazlo ANTES de crear el widget
    if st.session_state.get("__adm_clear", False):
        st.session_state.pop("__adm_clear", None)
        st.session_state.pop("__adm_pwd", None)  # limpiar valor previo

    with st.sidebar:
        st.markdown("### 🔒 Acceso administrador")

        if not is_admin_authenticated():
            # Widget de password con label oculto para evitar prompt del navegador
            pwd = st.text_input(
                label="__admin_code__",                 # label interno
                type="password",
                key="__adm_pwd",                        # key estable
                label_visibility="collapsed",
                placeholder="Ingrese código"
            )

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("Ingresar", use_container_width=True):
                    if st.session_state.get("__adm_pwd", "") == ADMIN_PASS:
                        st.session_state[ADMIN_SESSION_KEY] = True
                        st.session_state["__adm_clear"] = True
                        st.success("Acceso concedido.")
                        st.rerun()
                    else:
                        st.error("Código incorrecto.")

            with col2:
                if st.button("Limpiar", use_container_width=True):
                    st.session_state["__adm_clear"] = True
                    st.rerun()

        else:
            st.success("Acceso administrador activo.")
            if st.button("Cerrar sesión", use_container_width=True):
                st.session_state[ADMIN_SESSION_KEY] = False
                st.session_state["__adm_clear"] = True
                st.rerun()


# --- Configuración general ---
st.set_page_config(page_title="Gestión de Hospedaje", page_icon="🏠", layout="wide")

#Gestion credenciales de acceso.
# --- AUTENTICACIÓN INICIAL (PROFESIONAL / HARD-CODE) ---
def login_screen():
    st.markdown("## 🔐 Autenticación requerida")
    st.markdown("Ingrese sus credenciales para acceder al sistema.")

    with st.form("login_form"):
        usuario = st.text_input("Usuario", key="login_user")
        clave = st.text_input("Contraseña", type="password", key="login_pass")
        submitted = st.form_submit_button("Ingresar")

    if submitted:
        valid_users = {
            "Gonzalo": "Adriana1979.",
            "Amalia": "1979gonzalo"
        }

        if usuario in valid_users and clave == valid_users[usuario]:
            st.session_state["logged_in"] = True
            st.session_state["usuario_actual"] = usuario
            st.success("Acceso concedido.")
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos.")

# Inicializar estado
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

# Mostrar login si aún no está autenticado
if not st.session_state["logged_in"]:
    login_screen()
    st.stop()   # ⛔ DETIENE todo lo que viene después hasta iniciar sesión

#------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "hospedaje.db"

# --- Inicialización BD ---
db = Database(db_path=DB_PATH, project_root=PROJECT_ROOT)
db.ensure_database()

#Backup automático de base de datos
# Backup automático al iniciar (Railway)
try:
    db.backup_database()
except Exception as e:
    st.warning(f"No se pudo crear backup automático: {e}")
#----------------------------------

# --- Repositorios ---
repo_perfiles = PerfilUsuariosRepo(db)
repo_usuarios = UsuariosRepo(db)
repo_propietarios = PropietariosRepo(db)
repo_departamentos = DepartamentosRepo(db)
repo_conceptos = ConceptoGastosRepo(db)
repo_gastos = GastosRepo(db)
repo_reservas = ReservasRepo(db)

# --- Sidebar / navegación ---
st.sidebar.title("🏠 Gestión Hospedaje desarrollado por Gonzalo Estrella")

menu_principal = ["Catálogos", "Reservas", "Gastos", "Reportes", "Administración"]

# Default: Reservas
seccion = st.sidebar.radio(
    "Secciones",
    options=menu_principal,
    index=menu_principal.index("Reservas"),
    key="nav_seccion"
)

submenu = None

if seccion == "Catálogos":
    if st.session_state.get("nav_seccion_prev") != "Catálogos":
        st.session_state.pop("nav_cat", None)
        st.session_state["nav_seccion_prev"] = "Catálogos"
    submenu = st.sidebar.radio(
        "Catálogos",
        ["Propietarios", "Departamentos", "Conceptos de Gastos"],
        index=0,
        key="nav_cat"
    )

elif seccion == "Reservas":
    if st.session_state.get("nav_seccion_prev") != "Reservas":
        st.session_state.pop("nav_cat", None)
        st.session_state["nav_seccion_prev"] = "Reservas"
    submenu = st.sidebar.radio(
        "Reservas",
        ["Reservas", "Autorización de ingreso"],
        index=0,
        key="nav_reservas"
    )

elif seccion == "Gastos":
    if st.session_state.get("nav_seccion_prev") != "Gastos":
        st.session_state.pop("nav_cat", None)
        st.session_state["nav_seccion_prev"] = "Gastos"
    submenu = st.sidebar.radio(
        "Gastos",
        ["Gastos"],
        index=0,
        key="nav_gastos"
    )

elif seccion == "Reportes":
    if st.session_state.get("nav_seccion_prev") != "Reportes":
        st.session_state.pop("nav_cat", None)
        st.session_state["nav_seccion_prev"] = "Reportes"
    submenu = st.sidebar.radio(
        "Reportes",
        ["Reservas", "Gastos", "Diario", "Disponibilidad", "Reservas con saldo pendiente"],
        index=0,
        key="nav_reportes"
    )

elif seccion == "Administración":
    admin_login_widget()
    if is_admin_authenticated():
        if st.session_state.get("nav_seccion_prev") != "Administración":
            st.session_state.pop("nav_cat", None)
            st.session_state["nav_seccion_prev"] = "Administración"
        submenu = st.sidebar.radio(
            "Administración",
            ["Usuarios", "Base de datos", "Saldo inicial", "Importar Excel", "Limpiar base de datos FULL","Limpiar base de datos TRX"],
            index=0,
            key="nav_admin"
        )
    else:
        submenu = None
        st.sidebar.info("Ingrese la clave para habilitar los submenús de Administración.")

st.sidebar.markdown("---")
if st.sidebar.button("🧹 Limpiar sesión (recarga UI)"):
    st.session_state.clear()
    st.success("Sesión limpiada. (Los datos están en SQLite)")

# --- Router ---
if seccion == "Administración":
    if not is_admin_authenticated():
        st.warning("🔒 Sección protegida. Ingrese la clave en el panel lateral para continuar.")
    else:
        if submenu == "Usuarios":
            ui_admin_usuarios(repo_perfiles, repo_usuarios)
        elif submenu == "Base de datos":
            ui_admin_base_datos(db, PROJECT_ROOT)
        elif submenu == "Saldo inicial":
            ui_admin_saldo_inicial(db)
        elif submenu == "Importar Excel":
            ui_admin_importar_excel(db)
        elif submenu == "Limpiar base de datos FULL":
            ui_admin_limpiar_bd(db)
        elif submenu == "Limpiar base de datos TRX":
            ui_admin_limpiar_bd_2(db)

elif seccion == "Catálogos":
    if submenu == "Propietarios":
        cat.ui_cat_propietarios(repo_propietarios)
    elif submenu == "Departamentos":
        cat.ui_cat_departamentos(repo_departamentos, repo_propietarios)
    elif submenu == "Conceptos de Gastos":
        cat.ui_cat_conceptos_gastos(repo_conceptos)

elif seccion == "Reservas":
    if submenu == "Reservas":
        ui_reservas(repo_reservas, repo_departamentos)
    elif submenu == "Autorización de ingreso":
        ui_autorizacion_ingreso(db, PROJECT_ROOT)

elif seccion == "Gastos":
    if submenu == "Gastos":
        cat.ui_cat_gastos(repo_gastos, repo_conceptos)

elif seccion == "Reportes":
    if submenu == "Reservas":
        ui_rep_reservas(db)
    elif submenu == "Gastos":
        ui_rep_gastos(db)
    elif submenu == "Diario":
        ui_rep_diario(db)
    elif submenu == "Disponibilidad":
        ui_rep_disponibilidad(db)    
    elif submenu == "Reservas con saldo pendiente":
        ui_rep_reservas_saldo_pendiente(db)
