from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass
class PerfilUsuario:
    descripcion: str

@dataclass
class Usuario:
    nombre: str
    codPerfil: int

@dataclass
class Propietario:
    nombre: str

@dataclass
class Departamento:
    numero: str
    torre: Optional[str]
    piso: Optional[str]
    codPropietario: Optional[int]
    esPropio: int = 1   # 1 = propio, 0 = ajeno


@dataclass
class ConceptoGasto:
    descripcion: str

@dataclass
class Gasto:
    fecha: date
    detalle: str
    valor: float
    codConcepto: int

@dataclass
class Reserva:
    fecha: date
    idCliente: Optional[str]
    nombreCliente: str
    ciudad: Optional[str]
    celular: Optional[str]
    codigoDepartamento: int
    fechaInicio: date
    fechaFin: date
    numeroNoches: int
    valorNoche: float
    totalEstadia: float
    valorLimpieza: float
    comision: float
    numeroPersonas: int          # 👈 NUEVO
    estado: str

@dataclass
class AbonoReserva:
    numeroReserva: int
    fecha: date
    monto: float
    detalle: Optional[str] = None