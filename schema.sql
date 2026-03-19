PRAGMA foreign_keys = ON;

-- ===== PERFILES =====
CREATE TABLE IF NOT EXISTS perfilUsuarios (
    codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    descripcion TEXT NOT NULL UNIQUE
);

-- ===== USUARIOS =====
CREATE TABLE IF NOT EXISTS usuarios (
    codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    codPerfil INTEGER NOT NULL,
    FOREIGN KEY (codPerfil) REFERENCES perfilUsuarios(codigo)
);

-- ===== PROPIETARIOS =====
CREATE TABLE IF NOT EXISTS propietarios (
    codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL
);

-- ===== DEPARTAMENTOS =====
CREATE TABLE IF NOT EXISTS departamentos (
    codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL,
    torre TEXT,
    piso TEXT,
    codPropietario INTEGER,
    esPropio INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (codPropietario) REFERENCES propietarios(codigo)
);

-- ===== CONCEPTOS DE GASTOS =====
CREATE TABLE IF NOT EXISTS conceptoGastos (
    codigo INTEGER PRIMARY KEY AUTOINCREMENT,
    descripcion TEXT NOT NULL UNIQUE
);

-- ===== GASTOS =====
CREATE TABLE IF NOT EXISTS gastos (
    numero INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    detalle TEXT,
    valor REAL NOT NULL DEFAULT 0,
    codConcepto INTEGER NOT NULL,
    FOREIGN KEY (codConcepto) REFERENCES conceptoGastos(codigo)
);

-- ===== RESERVAS =====
CREATE TABLE IF NOT EXISTS reservas (
    numero INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    idCliente TEXT,
    nombreCliente TEXT NOT NULL,
    ciudad TEXT,
    celular TEXT,
    codigoDepartamento INTEGER NOT NULL,
    fechaInicio TEXT NOT NULL,
    fechaFin TEXT NOT NULL,
    numeroNoches INTEGER NOT NULL DEFAULT 0,
    valorNoche REAL NOT NULL DEFAULT 0,
    totalEstadia REAL NOT NULL DEFAULT 0,
    valorLimpieza REAL NOT NULL DEFAULT 0,
    comision REAL NOT NULL DEFAULT 0,
    numeroPersonas INTEGER NOT NULL DEFAULT 1,
    estado TEXT NOT NULL DEFAULT 'Pendiente',
    FOREIGN KEY (codigoDepartamento) REFERENCES departamentos(codigo)
);

-- ===== SALDO INICIAL =====
CREATE TABLE IF NOT EXISTS saldoInicial (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    fecha TEXT NOT NULL,
    monto REAL NOT NULL
);

-- ===== ABONOS RESERVA =====
CREATE TABLE IF NOT EXISTS abonosReserva (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numeroReserva INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    monto REAL NOT NULL,
    detalle TEXT,
    FOREIGN KEY(numeroReserva) REFERENCES reservas(numero)
);

-- ===== ÍNDICES =====
CREATE INDEX IF NOT EXISTS ix_reservas_depto_ini_fin   ON reservas (codigoDepartamento, fechaInicio, fechaFin);
CREATE INDEX IF NOT EXISTS ix_reservas_fechaInicio     ON reservas (fechaInicio);
CREATE INDEX IF NOT EXISTS ix_reservas_fechaFin        ON reservas (fechaFin);
CREATE INDEX IF NOT EXISTS ix_reservas_depto_fecha     ON reservas (codigoDepartamento, fecha);
CREATE INDEX IF NOT EXISTS ix_reservas_fecha           ON reservas (fecha);