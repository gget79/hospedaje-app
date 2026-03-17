PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS perfilUsuarios (
    codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    descripcion TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS usuarios (
    codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    codPerfil INTEGER NOT NULL,
    FOREIGN KEY (codPerfil) REFERENCES perfilUsuarios(codigo)
);

CREATE TABLE IF NOT EXISTS propietarios (
    codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS departamentos (
    codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL,
    torre TEXT,
    piso TEXT,
    codPropietario INTEGER,
    FOREIGN KEY (codPropietario) REFERENCES propietarios(codigo)
);

CREATE TABLE IF NOT EXISTS conceptoGastos (
    codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    descripcion TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS gastos (
    numero INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,            -- ISO8601 (YYYY-MM-DD)
    detalle TEXT,
    valor REAL NOT NULL DEFAULT 0,
    codConcepto INTEGER NOT NULL,
    FOREIGN KEY (codConcepto) REFERENCES conceptoGastos(codigo)
);

CREATE TABLE IF NOT EXISTS reservas (
    numero INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,            -- fecha de registro (ISO8601)
    idCliente TEXT,
    nombreCliente TEXT NOT NULL,
    ciudad TEXT,
    celular TEXT,
    codigoDepartamento INTEGER NOT NULL,
    fechaInicio TEXT NOT NULL,      -- ISO8601
    fechaFin TEXT NOT NULL,         -- ISO8601
    numeroNoches INTEGER NOT NULL DEFAULT 0,
    valorNoche REAL NOT NULL DEFAULT 0,
    totalEstadia REAL NOT NULL DEFAULT 0,
    valorLimpieza REAL NOT NULL DEFAULT 0,
    comision REAL NOT NULL DEFAULT 0,
    numeroPersonas INTEGER NOT NULL DEFAULT 1,  -- 👈 NUEVO
    estado TEXT NOT NULL DEFAULT 'Pendiente',
    FOREIGN KEY (codigoDepartamento) REFERENCES departamentos(codigo)
);

-- Saldo inicial: un solo registro (id = 1)
CREATE TABLE IF NOT EXISTS saldoInicial (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    fecha TEXT NOT NULL,  -- ISO YYYY-MM-DD
    monto REAL NOT NULL
);

-- Departamento propio (1) o ajeno (0)
ALTER TABLE departamentos ADD COLUMN esPropio INTEGER NOT NULL DEFAULT 1;

-- get.sn 
-- Acelera cruces por depto + rango
CREATE INDEX IF NOT EXISTS ix_reservas_depto_ini_fin
ON reservas (codigoDepartamento, fechaInicio, fechaFin);

-- Índices por fechas (si no existen)
CREATE INDEX IF NOT EXISTS ix_reservas_fechaInicio ON reservas (fechaInicio);
CREATE INDEX IF NOT EXISTS ix_reservas_fechaFin    ON reservas (fechaFin);

-- Generador de fechas (rango) por CTE recursivo (SQLite)
-- Uso: SELECT * FROM vw_fechas('2026-02-23', '2026-03-29');
DROP VIEW IF EXISTS vw_fechas;
CREATE VIEW vw_fechas AS
WITH RECURSIVE fechas(d, fin) AS (
  SELECT NULL, NULL  -- placeholder para permitir parámetros vía WHERE
)
SELECT NULL AS d, NULL AS fin;
-- Nota: SQLite no soporta vistas parametrizadas nativamente;
-- por eso, en repositorio generamos el CTE en la consulta directamente.
--get.en 

--get01.sn 
-- Reservas: índices de rango y depto
CREATE INDEX IF NOT EXISTS ix_reservas_depto_fecha ON reservas (codigoDepartamento, fecha);
CREATE INDEX IF NOT EXISTS ix_reservas_fecha       ON reservas (fecha);

-- Gastos: asegura columna y índice por depto/fecha
-- (Solo si NO tienes la columna; si ya existe, omite este ALTER)
-- ALTER TABLE gastos ADD COLUMN codigoDepartamento INTEGER;

CREATE INDEX IF NOT EXISTS ix_gastos_depto_fecha ON gastos (codigoDepartamento, fecha);

-- Reservas: por fecha y/o depto
CREATE INDEX IF NOT EXISTS ix_reservas_fecha             ON reservas (fecha);
CREATE INDEX IF NOT EXISTS ix_reservas_depto_fecha       ON reservas (codigoDepartamento, fecha);

--get01.en 
CREATE TABLE IF NOT EXISTS abonosReserva (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numeroReserva INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    monto REAL NOT NULL,
    detalle TEXT,
    FOREIGN KEY(numeroReserva) REFERENCES reservas(numero)
);