# apps/solicitudes/services/generar_reportes_solicitudes.py
#
# Reporte descargable de solicitudes (PDF y Excel). Mismos filtros e
# indicadores que la pantalla de Reportes (services/estadisticas.py).
#
#   PDF   → encabezado (período + filtros) · resumen · resumen por
#           estación · detalle de solicitudes.
#   Excel → hojas "Resumen", "Por estación" y "Detalle".

from core.fechas import formatear_fecha

from . import formato_reportes as fmt
from .estadisticas import (
    calcular_indicadores, describir_filtros, resumen_por_estacion,
    solicitudes_filtradas, texto_periodo,
)


TITULO = "Reporte de solicitudes"


# ------------------------------------------------
# DATOS
# ------------------------------------------------

def _detalle(filtros: dict):
    return (
        solicitudes_filtradas(filtros)
        .select_related("consumidor__user", "estacion_servicio", "municipio")
        .order_by("fecha_creacion")
    )


def _tasa_txt(v) -> str:
    return "—" if v is None else f"{v} %".replace(".", ",")


def _indicadores(ind: dict) -> list[tuple[str, object]]:
    return [
        ("Total de solicitudes",  ind["total"]),
        ("Litros despachados",    ind["litros_despachados"]),
        ("Aprobadas alguna vez",  ind["aprobadas_alguna_vez"]),
        ("Rechazadas",            ind["rechazadas"]),
        ("Tasa de aprobación",    _tasa_txt(ind["tasa_aprobacion"])),
        ("Tasa de rechazo",       _tasa_txt(ind["tasa_rechazo"])),
    ]


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _indicadores_pdf(ind: dict) -> list[tuple[str, str]]:
    return [
        ("Total de solicitudes",  _miles(ind["total"])),
        ("Litros despachados",    f"{_miles(ind['litros_despachados'])} L"),
        ("Aprobadas alguna vez",  _miles(ind["aprobadas_alguna_vez"])),
        ("Rechazadas",            _miles(ind["rechazadas"])),
        ("Tasa de aprobación",    _tasa_txt(ind["tasa_aprobacion"])),
        ("Tasa de rechazo",       _tasa_txt(ind["tasa_rechazo"])),
    ]


def _lineas_encabezado(filtros: dict) -> list[str]:
    return [
        texto_periodo(filtros["desde"], filtros["hasta"]),
        " · ".join(describir_filtros(filtros)),
    ]


def _consumidor(s) -> str:
    try:
        return s.consumidor.user.nombre_completo()
    except AttributeError:
        return "—"


def nombre_archivo_solicitudes(filtros: dict, extension: str) -> str:
    return f"reporte_solicitudes_{filtros['desde']:%Y-%m-%d}_{filtros['hasta']:%Y-%m-%d}.{extension}"


CAB_ESTACION = ["Estación", "Despachos", "Litros Gasolina", "Litros Diésel", "Total litros"]
CAB_DETALLE  = [
    "N° solicitud", "Consumidor", "Combustible", "Litros sol.", "Litros apr.",
    "Litros desp.", "Estado", "Municipio", "Estación",
    "Creación", "Aprobación", "Despacho",
]


# ------------------------------------------------
# PDF
# ------------------------------------------------

def generar_pdf_solicitudes(filtros: dict) -> bytes:
    qs = solicitudes_filtradas(filtros)
    ind = calcular_indicadores(qs)

    elementos = [
        fmt.recuadro_resumen(_indicadores_pdf(ind)),
    ]

    por_estacion = resumen_por_estacion(qs)
    elementos.append(fmt.subtitulo("Resumen por estación (litros despachados)"))
    if por_estacion:
        elementos.append(fmt.tabla(
            CAB_ESTACION,
            [[e["estacion"], e["despachos"], f"{e['gasolina']} L", f"{e['diesel']} L", f"{e['total']} L"]
             for e in por_estacion],
            anchos_cm=[10.7, 4, 4, 4, 4],
            numericas=frozenset({1, 2, 3, 4}),
        ))
    else:
        elementos.append(fmt.nota("Sin despachos en el período."))

    elementos.append(fmt.subtitulo("Detalle de solicitudes"))
    elementos.append(fmt.tabla(
        CAB_DETALLE,
        [[
            str(s.id_publico)[:8].upper(),
            _consumidor(s),
            s.get_tipo_combustible_display(),
            f"{s.litros_solicitados} L",
            f"{s.litros_aprobados} L" if s.litros_aprobados is not None else "—",
            f"{s.litros_despachados} L" if s.litros_despachados is not None else "—",
            s.get_estado_display(),
            s.municipio.nombre if s.municipio else "—",
            s.estacion_servicio.nombre if s.estacion_servicio else "—",
            formatear_fecha(s.fecha_creacion),
            formatear_fecha(s.fecha_aprobacion),
            formatear_fecha(s.fecha_despacho),
        ] for s in _detalle(filtros)],
        # Suma = 26.7 cm (ancho útil de la hoja apaisada)
        anchos_cm=[2.0, 3.3, 2.3, 1.5, 1.5, 1.6, 2.0, 2.5, 3.2, 2.2, 2.3, 2.3],
        numericas=frozenset({3, 4, 5}),
    ))

    return fmt.construir_pdf(TITULO, _lineas_encabezado(filtros), elementos)


# ------------------------------------------------
# EXCEL
# ------------------------------------------------

def generar_excel_solicitudes(filtros: dict) -> bytes:
    qs = solicitudes_filtradas(filtros)
    wb = fmt.nuevo_libro()

    fmt.hoja_resumen(wb, TITULO, _lineas_encabezado(filtros), _indicadores(calcular_indicadores(qs)))

    fmt.hoja_tabla(
        wb, "Por estación", CAB_ESTACION,
        [[e["estacion"], e["despachos"], e["gasolina"], e["diesel"], e["total"]]
         for e in resumen_por_estacion(qs)],
        anchos=[36, 12, 16, 16, 14],
        formatos={1: fmt.FMT_ENTERO, 2: fmt.FMT_ENTERO, 3: fmt.FMT_ENTERO, 4: fmt.FMT_ENTERO},
    )

    fmt.hoja_tabla(
        wb, "Detalle", CAB_DETALLE,
        [[
            str(s.id_publico)[:8].upper(),
            _consumidor(s),
            s.get_tipo_combustible_display(),
            s.litros_solicitados,
            s.litros_aprobados,
            s.litros_despachados,
            s.get_estado_display(),
            s.municipio.nombre if s.municipio else None,
            s.estacion_servicio.nombre if s.estacion_servicio else None,
            s.fecha_creacion,
            s.fecha_aprobacion,
            s.fecha_despacho,
        ] for s in _detalle(filtros)],
        anchos=[13, 30, 12, 11, 11, 11, 13, 18, 28, 17, 17, 17],
        formatos={
            3: fmt.FMT_ENTERO, 4: fmt.FMT_ENTERO, 5: fmt.FMT_ENTERO,
            9: fmt.FMT_FECHA_HORA, 10: fmt.FMT_FECHA_HORA, 11: fmt.FMT_FECHA_HORA,
        },
    )

    return fmt.libro_a_bytes(wb)

