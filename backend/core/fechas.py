# core/fechas.py
#
# Formato de fechas para todo lo que se muestra fuera de la API
# (emails, PDFs, Excel, dashboard).
#
# Con USE_TZ=True, los datetimes que vienen de la base y timezone.now()
# están en UTC: formatearlos directo con strftime muestra la hora UTC
# (+4 h respecto de La Paz, y de noche hasta el día siguiente). Todo
# pasa primero por timezone.localtime(), que usa TIME_ZONE
# (America/La_Paz).
#
# Los nombres de meses van en una lista fija en vez de %B/%b con
# setlocale: el contenedor de Railway puede no tener el locale "es"
# instalado, y strftime caería al inglés sin avisar.

from datetime import date, datetime, time

from django.utils import timezone


MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

MESES_CORTOS = [
    "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]

SIN_FECHA = "—"


def a_local(valor):
    """
    Datetime aware → hora local. Un date, un datetime naive o None
    se devuelven tal cual (no hay zona horaria que convertir).
    """
    if isinstance(valor, datetime) and timezone.is_aware(valor):
        return timezone.localtime(valor)
    return valor


def formatear_fecha(valor, vacio: str = SIN_FECHA) -> str:
    """dd/mm/aaaa. Acepta date o datetime."""
    if valor is None:
        return vacio
    return a_local(valor).strftime("%d/%m/%Y")


def formatear_fecha_hora(valor, vacio: str = SIN_FECHA) -> str:
    """dd/mm/aaaa HH:MM en hora local."""
    if valor is None:
        return vacio
    return a_local(valor).strftime("%d/%m/%Y %H:%M")


def formatear_dia_mes(valor) -> str:
    """dd/mm (ejes de gráficos)."""
    return a_local(valor).strftime("%d/%m")


def formatear_fecha_larga(valor) -> str:
    """'27 de septiembre de 2026'."""
    valor = a_local(valor)
    return f"{valor.day} de {MESES[valor.month - 1]} de {valor.year}"


def formatear_mes_anio(valor) -> str:
    """'Sep 2026' (etiquetas de la evolución mensual)."""
    valor = a_local(valor)
    return f"{MESES_CORTOS[valor.month - 1]} {valor.year}"


def ahora_local() -> datetime:
    """timezone.now() ya convertido a hora local, para formatear."""
    return timezone.localtime()


def inicio_dia_local(dia: date) -> datetime:
    """
    Medianoche LOCAL de `dia`, como datetime aware. Para filtrar
    "desde hoy" / "desde el 1° del mes" con __gte sin que la
    medianoche sea la de UTC (20:00 del día anterior en La Paz).
    """
    return timezone.make_aware(datetime.combine(dia, time.min))
