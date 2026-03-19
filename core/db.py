from __future__ import annotations
from pathlib import Path
import sqlite3
import pandas as pd

class Database:
    """
    Encapsula la conexión SQLite y asegura que el esquema exista.
    Lee el esquema desde `schema.sql` si está disponible.
    También provee utilitarios de migración y limpieza.
    """

    def __init__(self, db_path: Path, project_root: Path) -> None:
        import os

        # --- Detectar si estamos en Render ---
        RENDER = os.environ.get("RENDER", None) is not None

        if RENDER:
            # En Render la base debe vivir SIEMPRE en el disco persistente
            DATA_DIR = Path("/opt/render/project/src/data")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self.db_path = DATA_DIR / "database.db"
        else:
            # En local sigue usando el path normal
            self.db_path = db_path

        self.project_root = project_root
        self.data_dir = self.db_path.parent
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ---- Conexión ----
    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    # ---- Esquema ----
    def _load_schema_sql(self) -> str:
        schema_file = self.project_root / "schema.sql"
        if schema_file.exists():
            return schema_file.read_text(encoding="utf-8")
        return ""

    def initialize_schema(self) -> None:
        sql = self._load_schema_sql()
        if not sql.strip():
            return
        with self.connect() as conn:
            conn.executescript(sql)
            conn.commit()

    def ensure_column(self, table: str, column: str, definition: str) -> None:
        """
        Garantiza que `table.column` exista; si no, la crea con:
        ALTER TABLE <table> ADD COLUMN <column> <definition>
        """
        with self.connect() as conn:
            cur = conn.execute(f"PRAGMA table_info({table});")
            cols = {row[1] for row in cur.fetchall()}  # row[1] = name
            if column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition};")
                conn.commit()

    def ensure_database(self) -> None:
        """
        Valida que la BD exista y tenga el esquema. Si falta algo, lo crea.
        Además ejecuta migraciones (p.ej., columnas nuevas).
        """
        needs_init = not self.db_path.exists()
        if needs_init:
            self.initialize_schema()
        else:
            # Verificamos existencia de tablas mínimas
            required_tables = [
                "perfilUsuarios", "usuarios", "propietarios", "departamentos",
                "conceptoGastos", "gastos", "reservas"
            ]
            with self.connect() as conn:
                cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
                existing = {row[0] for row in cur.fetchall()}
            if not set(required_tables).issubset(existing):
                self.initialize_schema()

        # ... dentro de ensure_database()
        required_tables = [
            "perfilUsuarios", "usuarios", "propietarios", "departamentos",
            "conceptoGastos", "gastos", "reservas", "saldoInicial"  # 👈 asegura saldoInicial
        ]
        # ---- Migraciones: garantizar nuevas columnas ----
        self.ensure_column("reservas", "numeroPersonas", "INTEGER NOT NULL DEFAULT 1")
        self.ensure_column("reservas", "autorizacionSolicitada", "INTEGER NOT NULL DEFAULT 0")
        # NUEVO: tipo de propiedad de departamento (1 propio, 0 ajeno)
        self.ensure_column("departamentos", "esPropio", "INTEGER NOT NULL DEFAULT 1")

    # ---- Helpers SQL ----
    def run(self, sql: str, params=None) -> None:
        with self.connect() as conn:
            conn.execute(sql, params or [])
            conn.commit()

    def fetchall(self, sql: str, params=None):
        with self.connect() as conn:
            cur = conn.execute(sql, params or [])
            return cur.fetchall()

    def fetch_df(self, sql: str, params=None) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(sql, conn, params=params or [])

    # ---- Limpieza de datos preservando perfiles FULL----
    def clear_data_preserve_perfiles(self) -> None:
        """
        Elimina datos de todas las tablas de negocio y reinicia autoincrementos,
        preservando la tabla perfilUsuarios.
        Orden de borrado respeta FK (hijas -> padres):
        - abonosReserva (hija de reservas)
        - reservas      (hija de departamentos)
        - gastos        (hija de conceptoGastos)
        - usuarios      (hija de perfilUsuarios)  -> se puede borrar sin tocar perfiles
        - departamentos (hijo de propietarios)
        - conceptoGastos
        - propietarios
        - saldoInicial  (se borra el registro id=1)
        También limpia sqlite_sequence si existe.
        """
        import sqlite3

        with self.connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            try:
                # Inicia transacción
                conn.execute("BEGIN;")

                # --- Tablas HIJAS primero ---
                # abonosReserva depende de reservas
                try:
                    conn.execute("DELETE FROM abonosReserva;")
                except sqlite3.OperationalError:
                    # La tabla aún no existe en algunas instalaciones
                    pass

                # reservas depende de departamentos
                conn.execute("DELETE FROM reservas;")

                # gastos depende de conceptoGastos
                conn.execute("DELETE FROM gastos;")

                # usuarios depende de perfilUsuarios (perfiles se preservan)
                conn.execute("DELETE FROM usuarios;")

                # --- Padres y catálogos ---
                conn.execute("DELETE FROM departamentos;")
                conn.execute("DELETE FROM conceptoGastos;")
                conn.execute("DELETE FROM propietarios;")

                # --- Saldo inicial (se preserva la tabla, pero se limpia el registro) ---
                try:
                    conn.execute("DELETE FROM saldoInicial WHERE id = 1;")
                except sqlite3.OperationalError:
                    # Si no existe, lo ignoramos
                    pass

                # --- Reiniciar autoincrementos (si sqlite_sequence existe) ---
                try:
                    conn.execute(
                        "DELETE FROM sqlite_sequence WHERE name IN "
                        "('abonosReserva','reservas','gastos','usuarios','departamentos','conceptoGastos','propietarios','saldoInicial');"
                    )
                except sqlite3.OperationalError:
                    # sqlite_sequence no existe cuando no se usó AUTOINCREMENT
                    pass

                conn.commit()

            except Exception as e:
                conn.rollback()
                # Propaga el mensaje para mostrarlo en la UI
                raise RuntimeError(f"Error al limpiar BD: {e}")
            
    # ---- Limpieza de datos preservando perfiles TRANSACCIONES----
    def clear_data_preserve_perfiles_2(self) -> None:
            """
            Elimina datos de todas las tablas de negocio y reinicia autoincrementos,
            preservando la tabla perfilUsuarios.
            Orden de borrado respeta FK (hijas -> padres):
            - abonosReserva (hija de reservas)
            - reservas      (hija de departamentos)
            - gastos        (hija de conceptoGastos)
            - usuarios      (hija de perfilUsuarios)  -> se puede borrar sin tocar perfiles
            - departamentos (hijo de propietarios)
            - conceptoGastos
            - propietarios
            - saldoInicial  (se borra el registro id=1)
            También limpia sqlite_sequence si existe.
            """
            import sqlite3

            with self.connect() as conn:
                conn.execute("PRAGMA foreign_keys = ON;")
                try:
                    # Inicia transacción
                    conn.execute("BEGIN;")

                    # --- Tablas HIJAS primero ---
                    # abonosReserva depende de reservas
                    try:
                        conn.execute("DELETE FROM abonosReserva;")
                    except sqlite3.OperationalError:
                        # La tabla aún no existe en algunas instalaciones
                        pass

                    # reservas depende de departamentos
                    conn.execute("DELETE FROM reservas;")

                    # gastos depende de conceptoGastos
                    conn.execute("DELETE FROM gastos;")

                    
                    # --- Saldo inicial (se preserva la tabla, pero se limpia el registro) ---
                    try:
                        pass
                    except sqlite3.OperationalError:
                        # Si no existe, lo ignoramos
                        pass

                    # --- Reiniciar autoincrementos (si sqlite_sequence existe) ---
                    try:
                        conn.execute(
                            "DELETE FROM sqlite_sequence WHERE name IN "
                            "('abonosReserva','reservas','gastos');"
                        )
                    except sqlite3.OperationalError:
                        # sqlite_sequence no existe cuando no se usó AUTOINCREMENT
                        pass

                    conn.commit()

                except Exception as e:
                    conn.rollback()
                    # Propaga el mensaje para mostrarlo en la UI
                    raise RuntimeError(f"Error al limpiar BD: {e}")