from __future__ import annotations

import pandas as pd
from dataclasses import dataclass
from typing import Optional, List
from datetime import date, timedelta

from core.db import Database
from core.models import (
    PerfilUsuario, Usuario, Propietario, Departamento,
    ConceptoGasto, Gasto, Reserva
)
from core.utils import iso


# ===========================================================
#  CAJA
# ===========================================================
@dataclass
class CajaRepo:
    db: Database

    # ---- Saldo inicial (compatibilidad con tu UI/Admin) ----
    def get_saldo_inicial(self):
        row = self.db.fetchall("SELECT fecha, monto FROM saldoInicial WHERE id = 1;")
        if row:
            f, m = row[0]
            return f, float(m)
        return None

    def set_saldo_inicial(self, fecha: date, monto: float) -> None:
        # Crea la tabla si no existiera y guarda/actualiza el único registro (id=1)
        self.db.run("""
            CREATE TABLE IF NOT EXISTS saldoInicial (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                fecha TEXT NOT NULL,
                monto REAL NOT NULL
            );
        """)
        self.db.run("INSERT OR REPLACE INTO saldoInicial (id, fecha, monto) VALUES (1, ?, ?);",
                    (iso(fecha), float(monto)))

    # --- Determinar modo por selección (hard‑code: número '7' = PROPIO) ---
    def _modo_por_dep(self, dep_codigo: Optional[int]) -> str:
        """
        None  -> MIXTO  (Todos)
        numero == '7' -> PROPIO
        else  -> AJENO
        """
        if dep_codigo is None:
            return "MIXTO"
        try:
            df = self.db.fetch_df("SELECT numero FROM departamentos WHERE codigo = ?;", (dep_codigo,))
            if df is not None and not df.empty:
                numero = str(df.iloc[0]["numero"]).strip()
                return "PROPIO" if numero == "7" else "AJENO"
        except Exception:
            pass
        return "AJENO"

    # --- Movimientos Diario (Ingreso → Comisión → Limpieza → Gasto) ---
    def movimientos_diario(self, fi: date, ff: date, dep_codigo: Optional[int], modo: str) -> pd.DataFrame:
        """
        Devuelve: fecha, tipo, detalle, ingreso, egreso.
        - Ingreso/Comisión/Limpieza desde reservas (filtrables por depto).
        - Gastos globales SOLO si modo in {'PROPIO','MIXTO'}.
        """
        params_res = [fi.isoformat(), ff.isoformat()]
        dep_filter = ""
        if dep_codigo is not None:
            dep_filter = " AND r.codigoDepartamento = ? "
            params_res.append(dep_codigo)

        sql_ing = f"""
        SELECT
            r.fecha AS fecha,
            'Ingreso' AS tipo,
            printf('Reserva %s - Dpto %s', r.nombreCliente, d.numero) AS detalle,
            r.totalEstadia AS ingreso,
            0.0 AS egreso
        FROM reservas r
        JOIN departamentos d ON d.codigo = r.codigoDepartamento
        WHERE date(r.fecha) BETWEEN date(?) AND date(?)
          AND (r.estado IS NULL OR UPPER(r.estado) NOT IN ('CANCELADA','ANULADA'))
          {dep_filter}
        """

        sql_limp = f"""
        SELECT
            r.fecha AS fecha,
            'Limpieza' AS tipo,
            printf('Limpieza - Reserva %s - Dpto %s', r.nombreCliente, d.numero) AS detalle,
            0.0 AS ingreso,
            r.valorLimpieza AS egreso
        FROM reservas r
        JOIN departamentos d ON d.codigo = r.codigoDepartamento
        WHERE date(r.fecha) BETWEEN date(?) AND date(?)
          AND (r.estado IS NULL OR UPPER(r.estado) NOT IN ('CANCELADA','ANULADA'))
          {dep_filter}
        """

        sql_com = f"""
        SELECT
            r.fecha AS fecha,
            'Comisión' AS tipo,
            printf('Comisión - Reserva %s - Dpto %s', r.nombreCliente, d.numero) AS detalle,
            0.0 AS ingreso,
            r.comision AS egreso
        FROM reservas r
        JOIN departamentos d ON d.codigo = r.codigoDepartamento
        WHERE date(r.fecha) BETWEEN date(?) AND date(?)
          AND (r.estado IS NULL OR UPPER(r.estado) NOT IN ('CANCELADA','ANULADA'))
          {dep_filter}
        """

        dfs = []
        for sql, ps in [(sql_ing, list(params_res)), (sql_limp, list(params_res)), (sql_com, list(params_res))]:
            dfp = self.db.fetch_df(sql, tuple(ps))
            if dfp is not None and not dfp.empty:
                dfs.append(dfp)

        if modo in ("PROPIO", "MIXTO"):
            sql_gas = """
            SELECT
                g.fecha AS fecha,
                'Gasto' AS tipo,
                printf('%s: %s', c.descripcion, COALESCE(g.detalle,'')) AS detalle,
                0.0 AS ingreso,
                g.valor AS egreso
            FROM gastos g
            JOIN conceptoGastos c ON c.codigo = g.codConcepto
            WHERE date(g.fecha) BETWEEN date(?) AND date(?)
            """
            df_g = self.db.fetch_df(sql_gas, (fi.isoformat(), ff.isoformat()))
            if df_g is not None and not df_g.empty:
                dfs.append(df_g)

        if not dfs:
            return pd.DataFrame(columns=["fecha", "tipo", "detalle", "ingreso", "egreso"])

        df = pd.concat(dfs, ignore_index=True)

        # Normaliza tipo y orden requerido
        df["tipo"] = df["tipo"].astype(str).replace({"Comision": "Comisión"})
        orden_tipo = {"Ingreso": 0, "Comisión": 1, "Limpieza": 2, "Gasto": 3}
        df["__ord__"] = df["tipo"].map(lambda t: orden_tipo.get(t, 99))

        df["fecha"] = pd.to_datetime(df["fecha"])
        df = df.sort_values(["fecha", "__ord__"], ascending=[True, True]).reset_index(drop=True)
        df = df.drop(columns=["__ord__"], errors="ignore")
        return df

    # --- Saldo inicial (guardado / calculado / acumulado sin base) ---
    def saldo_inicial_guardado(self):
        try:
            df = self.db.fetch_df("SELECT fecha, monto FROM saldoInicial WHERE id = 1;")
        except Exception:
            return None, 0.0
        if df is None or df.empty:
            return None, 0.0
        f = pd.to_datetime(df.iloc[0]["fecha"]).date()
        return f, float(df.iloc[0]["monto"] or 0.0)

    def saldo_inicial_para_reporte(self, fi):
        f, m = self.saldo_inicial_guardado()
        return 0.0 if f is None else float(m)

    def saldo_inicial_calculado(self, fi: date, dep_codigo: Optional[int]) -> float:
        fecha_si, monto_si = self.saldo_inicial_guardado()
        if fecha_si is None:
            return 0.0
        if fi <= fecha_si:
            return float(monto_si)
        modo = self._modo_por_dep(dep_codigo)
        desde = fecha_si
        hasta = fi - timedelta(days=1)
        movs = self.movimientos_diario(desde, hasta, dep_codigo, modo)
        if movs.empty:
            return float(monto_si)
        ingresos = float(pd.to_numeric(movs["ingreso"], errors="coerce").sum())
        egresos = float(pd.to_numeric(movs["egreso"], errors="coerce").sum())
        return float(monto_si + ingresos - egresos)

    def saldo_inicial_acumulado_sin_base(self, fi: date, dep_codigo: Optional[int]) -> float:
        fecha_si, _ = self.saldo_inicial_guardado()
        if fecha_si is None or fi <= fecha_si:
            return 0.0
        modo = self._modo_por_dep(dep_codigo)
        desde = fecha_si
        hasta = fi - timedelta(days=1)
        movs = self.movimientos_diario(desde, hasta, dep_codigo, modo)
        if movs is None or movs.empty:
            return 0.0
        ingresos = float(pd.to_numeric(movs["ingreso"], errors="coerce").sum())
        egresos = float(pd.to_numeric(movs["egreso"], errors="coerce").sum())
        return float(ingresos - egresos)


# ===========================================================
#  PERFILES
# ===========================================================
class PerfilUsuariosRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, p: PerfilUsuario) -> None:
        self.db.run("INSERT INTO perfilUsuarios (descripcion) VALUES (?);", (p.descripcion,))

    def list_all(self) -> pd.DataFrame:
        return self.db.fetch_df("SELECT codigo, descripcion FROM perfilUsuarios ORDER BY codigo ASC;")


# ===========================================================
#  USUARIOS
# ===========================================================
class UsuariosRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, u: Usuario) -> None:
        self.db.run("INSERT INTO usuarios (nombre, codPerfil) VALUES (?, ?);", (u.nombre, u.codPerfil))

    def list_all(self) -> pd.DataFrame:
        sql = """
        SELECT u.codigo, u.nombre, p.descripcion AS perfil
        FROM usuarios u
        JOIN perfilUsuarios p ON p.codigo = u.codPerfil
        ORDER BY u.codigo ASC;
        """
        return self.db.fetch_df(sql)


# ===========================================================
#  PROPIETARIOS
# ===========================================================
class PropietariosRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, p: Propietario) -> None:
        self.db.run("INSERT INTO propietarios (nombre) VALUES (?);", (p.nombre,))

    def list_all(self) -> pd.DataFrame:
        return self.db.fetch_df("SELECT codigo, nombre FROM propietarios ORDER BY codigo ASC;")


# ===========================================================
#  DEPARTAMENTOS
# ===========================================================
class DepartamentosRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, d: Departamento) -> None:
        self.db.run(
            "INSERT INTO departamentos (numero, torre, piso, codPropietario, esPropio) VALUES (?, ?, ?, ?, ?);",
            (d.numero, d.torre, d.piso, d.codPropietario, int(d.esPropio))
        )

    def list_all(self) -> pd.DataFrame:
        sql = """
        SELECT d.codigo, d.numero, d.torre, d.piso,
               CASE WHEN d.esPropio=1 THEN 'Propio' ELSE 'Ajeno' END AS propiedad,
               p.nombre AS propietario
        FROM departamentos d
        LEFT JOIN propietarios p ON p.codigo = d.codPropietario
        ORDER BY d.numero;
        """
        return self.db.fetch_df(sql)


# ===========================================================
#  CONCEPTOS DE GASTOS
# ===========================================================
class ConceptoGastosRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, c: ConceptoGasto) -> None:
        self.db.run("INSERT INTO conceptoGastos (descripcion) VALUES (?);", (c.descripcion,))

    def list_all(self) -> pd.DataFrame:
        return self.db.fetch_df("SELECT codigo, descripcion FROM conceptoGastos ORDER BY codigo ASC;")


# ===========================================================
#  GASTOS
# ===========================================================
class GastosRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, g: Gasto) -> None:
        self.db.run(
            "INSERT INTO gastos (fecha, detalle, valor, codConcepto) VALUES (?, ?, ?, ?);",
            (iso(g.fecha), g.detalle, g.valor, g.codConcepto)
        )

    def list_all(self) -> pd.DataFrame:
        sql = """
        SELECT g.numero, g.fecha, c.descripcion AS concepto, g.detalle, g.valor
        FROM gastos g
        JOIN conceptoGastos c ON c.codigo = g.codConcepto
        ORDER BY g.fecha DESC, g.numero DESC;
        """
        return self.db.fetch_df(sql)


# ===========================================================
#  RESERVAS  ( + ABONOS )
# ===========================================================
class ReservasRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, r: Reserva) -> None:
        self.db.run(
            """
            INSERT INTO reservas
            (fecha, idCliente, nombreCliente, ciudad, celular, codigoDepartamento,
             fechaInicio, fechaFin, numeroNoches, valorNoche, totalEstadia,
             valorLimpieza, comision, numeroPersonas, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                iso(r.fecha), r.idCliente, r.nombreCliente, r.ciudad, r.celular,
                r.codigoDepartamento, iso(r.fechaInicio), iso(r.fechaFin), r.numeroNoches,
                r.valorNoche, r.totalEstadia, r.valorLimpieza, r.comision,
                r.numeroPersonas, r.estado
            )
        )

    def list_all(self) -> pd.DataFrame:
        # Mantenemos tu SELECT original con autorizacionSolicitada si existe.
        sql = """
        SELECT r.numero, r.fecha, r.idCliente, r.nombreCliente, r.ciudad, r.celular,
            d.numero AS departamento, r.fechaInicio, r.fechaFin, r.numeroNoches,
            r.valorNoche, r.totalEstadia, r.valorLimpieza, r.comision,
            r.numeroPersonas, r.autorizacionSolicitada, r.estado
        FROM reservas r
        JOIN departamentos d ON d.codigo = r.codigoDepartamento
        ORDER BY r.fecha DESC, r.numero DESC;
        """
        return self.db.fetch_df(sql)

    # ---------------- ABONOS: helpers internos ----------------
    def _ensure_abonos_table(self) -> None:
        self.db.run("""
        CREATE TABLE IF NOT EXISTS abonosReserva (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numeroReserva INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            monto REAL NOT NULL,
            detalle TEXT,
            FOREIGN KEY(numeroReserva) REFERENCES reservas(numero)
        );
        """)

    # ---------------- ABONOS: API pública ----------------
    def insert_abono(self, numero_reserva: int, fecha: date, monto: float, detalle: Optional[str]) -> None:
        self._ensure_abonos_table()
        self.db.run(
            "INSERT INTO abonosReserva (numeroReserva, fecha, monto, detalle) VALUES (?, ?, ?, ?);",
            (int(numero_reserva), iso(fecha), float(monto), detalle)
        )

    def listar_abonos(self, numero_reserva: int) -> pd.DataFrame:
        self._ensure_abonos_table()
        sql = """
            SELECT id, numeroReserva, fecha, monto, detalle
            FROM abonosReserva
            WHERE numeroReserva = ?
            ORDER BY fecha ASC, id ASC;
        """
        return self.db.fetch_df(sql, (int(numero_reserva),))

    def total_abonos(self, numero_reserva: int) -> float:
        df = self.listar_abonos(int(numero_reserva))
        if df is None or df.empty:
            return 0.0
        return float(pd.to_numeric(df["monto"], errors="coerce").fillna(0.0).sum())

    def saldo_pendiente(self, numero_reserva: int) -> float:
        # total = totalEstadia + valorLimpieza + comision
        df = self.db.fetch_df("""
            SELECT (totalEstadia + valorLimpieza) AS total
            FROM reservas
            WHERE numero = ?;
        """, (int(numero_reserva),))
        if df is None or df.empty:
            return 0.0
        total = float(df.iloc[0]["total"] or 0.0)
        abonado = self.total_abonos(int(numero_reserva))
        return max(total - abonado, 0.0)

    def reservas_con_saldo_pendiente(self) -> pd.DataFrame:
        self._ensure_abonos_table()
        # Evitamos HAVING; calculamos saldo en WHERE para soportar SQLite sin GROUP BY
        sql = """
        SELECT 
            r.numero,
            r.fecha,
            r.nombreCliente,
            d.numero AS departamento,
            (r.totalEstadia + r.valorLimpieza) AS total,
            COALESCE((SELECT SUM(a.monto) FROM abonosReserva a WHERE a.numeroReserva = r.numero), 0) AS abonado,
            ((r.totalEstadia + r.valorLimpieza)
             - COALESCE((SELECT SUM(a.monto) FROM abonosReserva a WHERE a.numeroReserva = r.numero), 0)
            ) AS saldoPendiente
        FROM reservas r
        JOIN departamentos d ON d.codigo = r.codigoDepartamento
        WHERE ((r.totalEstadia + r.valorLimpieza)
               - COALESCE((SELECT SUM(a.monto) FROM abonosReserva a WHERE a.numeroReserva = r.numero), 0)) > 0
        ORDER BY r.fecha DESC;
        """
        return self.db.fetch_df(sql)


# ===========================================================
#  DISPONIBILIDAD  (como en tu versión estable)
# ===========================================================
@dataclass
class DisponibilidadRepo:
    db: Database

    def disponibilidad_por_rango(self, fi: date, ff: date, codigos: Optional[List[int]] = None) -> pd.DataFrame:
        """
        Devuelve: codigoDepartamento, departamento (numero), fecha (YYYY-MM-DD), ocupado (0/1).
        Ocupado si existe reserva con: fechaInicio <= d < fechaFin y estado NOT IN ('Cancelada','Anulada').
        """
        base_sql = """
        WITH RECURSIVE rango(d) AS (
            SELECT date(?)              -- fi
            UNION ALL
            SELECT date(d, '+1 day') FROM rango WHERE d < date(?)  -- ff
        )
        SELECT
            dpt.codigo AS codigoDepartamento,
            dpt.numero AS departamento,
            r.d        AS fecha,
            CASE WHEN EXISTS (
                SELECT 1
                FROM reservas rsv
                WHERE rsv.codigoDepartamento = dpt.codigo
                  AND date(r.d) >= date(rsv.fechaInicio)
                  AND date(r.d) <  date(rsv.fechaFin)   -- día de salida es libre
                  AND (rsv.estado IS NULL OR UPPER(rsv.estado) NOT IN ('CANCELADA','ANULADA'))
            )
            THEN 1 ELSE 0 END AS ocupado
        FROM departamentos dpt
        CROSS JOIN rango r
        {FILTRO}
        ORDER BY dpt.numero, r.d;
        """
        params: list = [fi.isoformat(), ff.isoformat()]

        if codigos and len(codigos) > 0:
            placeholders = ",".join(["?"] * len(codigos))
            sql = base_sql.replace("{FILTRO}", f"WHERE dpt.codigo IN ({placeholders})")
            params = params + codigos
        else:
            sql = base_sql.replace("{FILTRO}", "")

        return self.db.fetch_df(sql, tuple(params))

    def pivot_calendario(self, df: pd.DataFrame) -> pd.DataFrame:
        """Matriz departamento × fecha con 'Libre'/'Ocupado'."""
        if df.empty:
            return df
        df2 = df.copy()
        df2["estado"] = df2["ocupado"].map(lambda x: "Ocupado" if int(x) else "Libre")
        tabla = df2.pivot(index="departamento", columns="fecha", values="estado").reset_index()
        # Orden natural por número de departamento si es posible
        try:
            tabla = tabla.sort_values(
                by="departamento",
                key=lambda s: s.astype(str).str.extract(r"(\d+)").astype(float).fillna(0).iloc[:, 0]
            )
        except Exception:
            pass
        return tabla