from __future__ import annotations
from pathlib import Path
import sqlite3
import pandas as pd

import shutil
from datetime import datetime


class Database:
    """
    Encapsula la conexión SQLite y asegura que el esquema exista.
    Lee el esquema desde `schema.sql` si está disponible.
    También provee utilitarios de migración y limpieza.
    """

    def __init__(self, db_path: Path, project_root: Path) -> None:
        import os

        # Detectar si estamos corriendo en Railway
        ON_RAILWAY = os.environ.get("RAILWAY_STATIC_URL") is not None

        if ON_RAILWAY:
            # Usar almacenamiento persistente real de Railway
            DATA_DIR = Path("/mnt/data")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self.db_path = DATA_DIR / "database.db"
        else:
            # Modo local (Windows / Linux / Mac)
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
        Valida que la BD exista y tenga el esquema correcto.
        Evita recrearla por error (especialmente en Railway).
        Ejecuta migraciones de columnas nuevas si faltan.
        """

        # ---- FIX para Railway: evitar BD vacía si el mount tarda ----
        if str(self.db_path).startswith("/mnt/data"):
            import time
            # Espera breve para permitir que Railway monte el filesystem persistente
            for _ in range(6):     # 3 segundos en total
                if self.db_path.exists():
                    break
                time.sleep(0.5)

        # ---- Si la BD REALMENTE no existe, inicializar schema ----
        needs_init = not self.db_path.exists()
        if needs_init:
            self.initialize_schema()
        else:
            # Verificar existencia de tablas mínimas
            required_tables = [
                "perfilUsuarios", "usuarios", "propietarios", "departamentos",
                "conceptoGastos", "gastos", "reservas", "saldoInicial",
                "abonosReserva"
            ]

            with self.connect() as conn:
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table';"
                )
                existing = {row[0] for row in cur.fetchall()}

            # Si falta alguna tabla importante, recrear schema
            if not set(required_tables).issubset(existing):
                self.initialize_schema()

        # ================================================================
        # MIGRACIONES DE COLUMNAS (AQUI YA EXISTE BD Y TABLAS)
        # ================================================================

        # En reservas
        self.ensure_column("reservas", "numeroPersonas", "INTEGER NOT NULL DEFAULT 1")
        self.ensure_column("reservas", "autorizacionSolicitada", "INTEGER NOT NULL DEFAULT 0")

        # En departamentos
        self.ensure_column("departamentos", "esPropio", "INTEGER NOT NULL DEFAULT 1")

        # (Si quieres migraciones futuras, las agregas aquí abajo)

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
                

    def backup_database(self, keep_last: int = 10) -> Path:
        """
        Crea un backup automático de la base de datos en /mnt/data/backups/.
        Mantiene solo los últimos 'keep_last' archivos.
        """
        backup_dir = self.data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"backup_{timestamp}.db"

        # Copiar la BD actual
        shutil.copy2(self.db_path, backup_path)

        # Limpiar backups antiguos
        backups = sorted(backup_dir.glob("backup_*.db"))
        if len(backups) > keep_last:
            to_delete = backups[:-keep_last]
            for old in to_delete:
                old.unlink()

        return backup_path