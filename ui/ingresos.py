# ui/ingresos.py (encabezado)
import os
import re
import sys
import time
import subprocess
import urllib.parse as urlparse
from pathlib import Path
from datetime import date

import pandas as pd
import streamlit as st
from docx2pdf import convert as docx_to_pdf  # conversión a PDF (Windows + Word)

from core.db import Database
from core.docgen import render_docx

from urllib.parse import quote as url_quote


def _reservas_join_dep_prop_df(db: Database) -> pd.DataFrame:
    sql = """
    SELECT
      r.numero           AS num_reserva,
      r.nombreCliente    AS huesped,
      r.fechaInicio      AS fecha_inicio,
      r.fechaFin         AS fecha_fin,
      r.numeroPersonas   AS num_personas,
      d.codigo           AS dep_id,
      d.numero           AS dep_num,
      COALESCE(p.nombre, '(Sin propietario)') AS propietario
    FROM reservas r
    JOIN departamentos d ON d.codigo = r.codigoDepartamento
    LEFT JOIN propietarios p ON p.codigo = d.codPropietario
    ORDER BY r.numero DESC;
    """
    return db.fetch_df(sql)

def _pick_template(project_root: Path, dep_num: str) -> Path:
    """
    Intenta usar templates/autorizacion_<DEPTO>.docx.
    Si no existe, usa templates/autorizacion_generica.docx
    """
    t_dir = project_root / "templates"
    specific = t_dir / f"autorizacion_{dep_num}.docx"
    if specific.exists():
        return specific
    generic = t_dir / "autorizacion_generica.docx"
    return generic

def _convert_docx_to_pdf_windows(docx_path: Path, pdf_path: Path) -> bool:
    """
    Convierte DOCX -> PDF en Windows inicializando COM para la sesión.
    1) Intenta con docx2pdf (misma sesión, con CoInitialize).
    2) Si falla, lanza un proceso separado: 'python -m docx2pdf'.
    Devuelve True si el PDF existe al final.
    """
    # Asegúrate de que no quede un PDF viejo con el mismo nombre
    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except Exception:
            pass

    # ---- Intento 1: docx2pdf en este proceso (inicializando COM)
    com_inited = False
    try:
        import ctypes  # solo Windows
        ctypes.windll.ole32.CoInitialize(None)
        com_inited = True
    except Exception:
        # Si falla la inicialización, continúa al intento de conversión; quizá no sea necesario en tu entorno
        pass

    try:
        docx_to_pdf(str(docx_path), str(pdf_path))
        if pdf_path.exists():
            return True
    except Exception as e:
        # Continúa con el fallback
        pass
    finally:
        if com_inited:
            try:
                import ctypes
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass

    # ---- Intento 2 (fallback): proceso separado que ejecuta el módulo docx2pdf
    try:
        res = subprocess.run(
            [sys.executable, "-m", "docx2pdf", str(docx_path), str(pdf_path)],
            capture_output=True, text=True, timeout=90, check=True
        )
        # Pequeña espera por si Word tarda en cerrar
        time.sleep(0.5)
        return pdf_path.exists()
    except Exception:
        return False


def ui_autorizacion_ingreso(db, project_root: Path):
    st.header("📝 Reservas → Autorización de ingreso")

    # ------------------ FASE 2: limpieza antes de crear widgets ------------------
    # Si al pulsar "Finalizar" marcamos la bandera, aquí limpiamos ANTES de instanciar los inputs
    if st.session_state.get("_autoriz_should_clear", False):
        # Opción 1: limpieza total
        # st.session_state.clear()
        # Preferimos limpieza selectiva para no perder otros estados globales no relacionados:
        for i in range(8):
            st.session_state.pop(f"p_nombre_{i}", None)
            st.session_state.pop(f"p_ced_{i}", None)
        st.session_state.pop("autoriz_last", None)
        # Desactivar bandera y continuar
        st.session_state["_autoriz_should_clear"] = False
        # Importante: forzar un rerun para que los widgets se reconstruyan sin valores previos
        st.rerun()

    # (Opcional) Nonce para forzar recreación de widgets si tu navegador te “mantiene” texto.
    # Lo incrementaremos cuando finalizas. Si no quieres usar nonce, elimina esta sección y su uso en keys.
    if "_autoriz_nonce" not in st.session_state:
        st.session_state["_autoriz_nonce"] = 0
    nonce = st.session_state["_autoriz_nonce"]

    df = _reservas_join_dep_prop_df(db)
    if df.empty:
        st.info("No hay reservas registradas.")
        return

    # Selector de reserva
    opciones = {
        f"N°{row.num_reserva} | {row.huesped} | Depto {row.dep_num} | {row.fecha_inicio}→{row.fecha_fin}": int(row.num_reserva)
        for _, row in df.iterrows()
    }
    etiqueta = st.selectbox("Reserva", list(opciones.keys()))
    num_reserva = opciones[etiqueta]

    # Fila seleccionada
    rsel = df[df["num_reserva"] == num_reserva].iloc[0]
    dep_num = str(rsel["dep_num"])
    propietario = str(rsel["propietario"])
    huesped = str(rsel["huesped"])
    num_personas = int(rsel["num_personas"])
    fecha_ingreso = str(rsel["fecha_inicio"])
    fecha_salida  = str(rsel["fecha_fin"])

    st.write(f"**Propietario:** {propietario}  |  **Departamento:** {dep_num}")

    # ------------------ FORMULARIO ------------------
    with st.form("form_autorizacion", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            fecha_doc = st.date_input("Fecha del documento", value=date.today())
        with col2:
            celular_admin = st.text_input("WhatsApp administración (formato +593...)", value="+593")

        st.caption("Ingresa hasta 8 personas (Nombre completo + Cédula). Una fila por persona.")
        personas = []
        for i in range(8):
            col_nom, col_id = st.columns([2, 1])
            with col_nom:
                # Nota: usamos nonce en la key para que, tras finalizar, las cajas se “recreen” limpias
                nombre_i = st.text_input(f"Nombre {i+1}", value="", key=f"p_nombre_{i}_{nonce}")
            with col_id:
                cedula_i = st.text_input(f"Cédula {i+1}", value="", key=f"p_ced_{i}_{nonce}")
            personas.append((nombre_i.strip(), cedula_i.strip()))

        enviado = st.form_submit_button("📄 Generar documento")
        if enviado:
            # Helper para nombres de archivo (slug)
            def _slug(s: str) -> str:
                return re.sub(r"[^A-Za-z0-9_-]+", "-", s.strip()).strip("-").lower()

            # Mapping para placeholders (sin HTML escapado)
            mapping = {
                "<<FECHA>>": fecha_doc.strftime("%Y-%m-%d"),
                "<<PROPIETARIO>>": propietario,
                "<<DEPTO>>": dep_num,
                "<<HUESPED>>": huesped,
                "<<NUM_PERSONAS>>": str(num_personas),
                "<<FECHA_INGRESO>>": fecha_ingreso,
                "<<FECHA_SALIDA>>":  fecha_salida,
            }

            # Placeholders por persona
            for idx, (n, c) in enumerate(personas, start=1):
                mapping[f"<<N{idx}>>"]  = n
                mapping[f"<<CI{idx}>>"] = c
                num_ = f"{idx}.-"
                linea = f"{num_} {n}    {c}" if (n or c) else ""
                mapping[f"<<L{idx}>>"] = linea

            # Plantilla
            tpl = _pick_template(project_root, dep_num)
            if not tpl.exists():
                st.error(f"No se encontró plantilla: {tpl.name}. Coloca una en {project_root/'templates'}.")
                st.stop()

            # Directorio de salida
            out_dir = project_root / "salidas" / "autorizaciones"
            out_dir.mkdir(parents=True, exist_ok=True)

            # Nombre de archivo
            fname_base = (
                f"autoriz_res-{int(num_reserva)}_dep-{_slug(dep_num)}_"
                f"huesped-{_slug(huesped)}_"
                f"ing-{fecha_ingreso.replace('-', '')}_sal-{fecha_salida.replace('-', '')}_"
                f"pax-{num_personas}_doc-{fecha_doc.strftime('%Y%m%d')}"
            )
            docx_path = out_dir / f"{fname_base}.docx"
            pdf_path  = out_dir / f"{fname_base}.pdf"

            # Generar DOCX
            try:
                render_docx(tpl, docx_path, mapping)
            except Exception as e:
                st.error(f"Error al generar el DOCX: {e}")
                st.stop()

            # Intentar convertir a PDF (solo Windows con Word)
            pdf_ok = False
            try:
                if os.name == "nt":
                    pdf_ok = _convert_docx_to_pdf_windows(docx_path, pdf_path)
            except Exception as e:
                pdf_ok = False
                st.warning(f"No se pudo convertir a PDF: {e}")

            # Marcar indicador en la reserva
            try:
                db.run("UPDATE reservas SET autorizacionSolicitada = 1 WHERE numero = ?;", (int(num_reserva),))
            except Exception as e:
                st.warning(f"No se pudo actualizar el indicador: {e}")

            # WhatsApp
            wa_text = (
                f"Solicitud de autorización de ingreso%0A"
                f"Reserva N° {num_reserva} | Depto {dep_num}%0A"
                f"Propietario: {propietario}%0A"
                f"Huésped: {huesped}%0A"
                f"Fecha doc: {fecha_doc.strftime('%Y-%m-%d')}%0A"
                f"Se adjunta autorización en {'PDF' if pdf_ok else 'DOCX'}."
            )
            num_wa = celular_admin.replace(" ", "")
            if num_wa.startswith("0"):
                num_wa = "+593" + num_wa[1:]
            wa_url = f"https://wa.me/{url_quote(num_wa)}?text={wa_text}"

            # Guardar para la sección de descarga
            st.session_state["autoriz_last"] = {
                "pdf_ok": bool(pdf_ok),
                "pdf_path": str(pdf_path),
                "docx_path": str(docx_path),
                "wa_url": wa_url,
            }
            st.success("Documento generado correctamente. Revisa las opciones de descarga y WhatsApp más abajo.")

    # ------------------ ACCIONES FUERA DEL FORM ------------------
    last = st.session_state.get("autoriz_last")
    if last:
        st.markdown("### 📄 Descarga / Envío")

        # Descarga priorizando PDF
        if last.get("pdf_ok", False):
            ruta = last.get("pdf_path")
            try:
                if ruta and os.path.exists(ruta):
                    with open(ruta, "rb") as f:
                        st.download_button(
                            "⬇️ Descargar autorización (PDF)",
                            data=f.read(),
                            file_name=Path(ruta).name,
                            mime="application/pdf",
                            use_container_width=True
                        )
                else:
                    st.warning("El PDF no existe en la ruta indicada.")
            except Exception as e:
                st.warning(f"No se pudo abrir el PDF para su descarga: {e}")
        else:
            ruta = last.get("docx_path")
            try:
                if ruta and os.path.exists(ruta):
                    with open(ruta, "rb") as f:
                        st.download_button(
                            "⬇️ Descargar autorización (DOCX)",
                            data=f.read(),
                            file_name=Path(ruta).name,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True
                        )
                else:
                    st.warning("El DOCX no existe en la ruta indicada.")
            except Exception as e:
                st.warning(f"No se pudo abrir el DOCX para su descarga: {e}")

        # WhatsApp
        if last.get("wa_url"):
            st.link_button("📲 Abrir WhatsApp para enviar", last["wa_url"], use_container_width=True)

        # Pie de ayuda
        ruta_mostrar = last.get("pdf_path") if last.get("pdf_ok") else last.get("docx_path")
        if ruta_mostrar:
            st.caption(
                "Si no tienes acceso a WhatsApp Web, el archivo quedó guardado en: "
                f"**{ruta_mostrar}**"
            )

        # ------------- BOTÓN FINALIZAR (Fase 1) -------------
        if st.button("Finalizar y limpiar formulario", type="primary", use_container_width=True):
            # Marcamos bandera para limpiar ANTES de recrear los widgets
            st.session_state["_autoriz_should_clear"] = True
            # También incrementamos el nonce para forzar nuevas keys de widgets
            st.session_state["_autoriz_nonce"] = st.session_state.get("_autoriz_nonce", 0) + 1
            # Limpiamos datos de salida
            st.session_state["autoriz_last"] = None
            st.success("Formulario limpiado.")
            st.rerun()
