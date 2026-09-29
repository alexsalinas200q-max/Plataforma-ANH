# apps/solicitudes/services/generar_reportes.py
#
# Reporte de consumidores de un MES calendario (hora local).
#
#   - TODOS        → todos los consumidores.
#   - CUPO_AGOTADO → cupo usado >= 120 L en ese mes, con la misma regla
#                    que validar_cupo (APROBADA + DESPACHADA por mes de
#                    fecha_aprobacion).
#   - BLOQUEADOS / EN_REVISION → según alerta_repetitividad (hoy solo se
#                    cambia a mano desde DetalleConsumidor). Agregan la
#                    columna "Motivo" (motivo_bloqueo).
#
# Con consumidor_id: reporte de UN consumidor (siempre con detalle).
#
# Por consumidor: solicitudes creadas en el mes (cualquier estado),
# litros despachados de esas mismas solicitudes (creadas en el mes, la
# misma base que el reporte de solicitudes, así los totales coinciden)
# y cupo usado (regla de validar_cupo: aprobado + despachado en el mes).
# Con incluir_detalle, además, sus solicitudes del mes. Todo sale de un
# queryset anotado + prefetch: la cantidad de queries es fija (2 sin
# detalle, 3 con detalle) sin importar cuántos consumidores haya.

import re
from datetime import date

from django.db.models import Count, IntegerField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce

from core.fechas import formatear_fecha, formatear_mes_anio_largo, rango_mes_local

from . import formato_reportes as fmt


FILTROS = {
    "TODOS":        "Todos los consumidores",
    "CUPO_AGOTADO": "Cupo mensual agotado",
    "BLOQUEADOS":   "Consumidores bloqueados",
    "EN_REVISION":  "Consumidores en revisión",
}

# Filtros por alerta_repetitividad (muestran la columna "Motivo")
FILTROS_ALERTA = {"BLOQUEADOS": "BLOQUEADO", "EN_REVISION": "EN_REVISION"}

NOTA_DEFINICIONES = (
    "Solicitudes y litros despachados: solicitudes creadas en el mes. "
    "Cupo usado: aprobado + despachado en el mes, según la regla de 120 L."
)


# ------------------------------------------------
# DATOS
# ------------------------------------------------

def get_consumidores(filtro: str, mes: date, con_solicitudes: bool = False,
                     consumidor_id: int | None = None):
    """
    Lista de ConsumidorPerfil del reporte, ordenada por litros
    despachados (mayor a menor). Cada perfil trae anotados
    `solicitudes_mes`, `litros_despachados_mes` y `cupo_usado_mes`, y
    con `con_solicitudes` también `solicitudes_del_mes` (lista).
    """
    from consumidores.models import ConsumidorPerfil
    from solicitudes.models import Solicitud
    from solicitudes.services.validar_cupo import CUPO_MENSUAL_LITROS, filtro_cupo_del_mes

    inicio, fin = rango_mes_local(mes)
    cero = Value(0, output_field=IntegerField())

    qs = (
        ConsumidorPerfil.objects
        .select_related("user", "municipio")
        .prefetch_related("documentos")
        .annotate(
            solicitudes_mes=Count(
                "solicitudes",
                filter=Q(solicitudes__fecha_creacion__gte=inicio,
                         solicitudes__fecha_creacion__lt=fin),
            ),
            litros_despachados_mes=Coalesce(
                Sum("solicitudes__litros_despachados",
                    filter=Q(solicitudes__estado=Solicitud.EstadoSolicitud.DESPACHADA,
                             solicitudes__fecha_creacion__gte=inicio,
                             solicitudes__fecha_creacion__lt=fin)),
                cero,
            ),
            cupo_usado_mes=Coalesce(
                Sum("solicitudes__litros_aprobados",
                    filter=filtro_cupo_del_mes(inicio, fin, prefijo="solicitudes__")),
                cero,
            ),
        )
        .order_by("-litros_despachados_mes", "user__apellido_paterno", "user__nombres")
    )

    if consumidor_id is not None:
        qs = qs.filter(pk=consumidor_id)

    if filtro == "CUPO_AGOTADO":
        qs = qs.filter(cupo_usado_mes__gte=CUPO_MENSUAL_LITROS)
    elif filtro in FILTROS_ALERTA:
        qs = qs.filter(alerta_repetitividad=FILTROS_ALERTA[filtro])

    if con_solicitudes:
        qs = qs.prefetch_related(Prefetch(
            "solicitudes",
            queryset=Solicitud.objects
                .filter(fecha_creacion__gte=inicio, fecha_creacion__lt=fin)
                .select_related("estacion_servicio")
                .order_by("fecha_creacion"),
            to_attr="solicitudes_del_mes",
        ))

    return list(qs)


def _ci(perfil) -> str:
    # documentos ya viene prefetcheado: .all() usa la caché (.first()
    # dispararía una query por consumidor).
    docs = perfil.documentos.all()
    if not docs:
        return "—"
    doc = docs[0]
    comp = f"-{doc.complemento_documento}" if doc.complemento_documento else ""
    return f"{doc.tipo_documento} {doc.numero_documento}{comp}"


def fila_consumidor(perfil) -> dict:
    from solicitudes.services.validar_cupo import CUPO_MENSUAL_LITROS
    return {
        "nombre":             perfil.user.nombre_completo(),
        "ci":                 _ci(perfil),
        "municipio":          perfil.municipio.nombre if perfil.municipio else "—",
        "solicitudes_mes":    perfil.solicitudes_mes,
        "litros_despachados": perfil.litros_despachados_mes,
        "cupo_usado":         perfil.cupo_usado_mes,
        "cupo_texto":         f"{perfil.cupo_usado_mes}/{CUPO_MENSUAL_LITROS} L",
        "estado_cuenta":      perfil.user.get_estado_cuenta_display(),
        "motivo":             perfil.motivo_bloqueo or "—",
    }


def titulo_reporte(filtro: str, mes: date) -> str:
    return f"Reporte de consumidores — {FILTROS[filtro]} — {formatear_mes_anio_largo(mes)}"


def nombre_archivo_consumidor(perfil, mes: date, extension: str) -> str:
    """reporte_consumidor_<CI>_AAAA-MM.<ext> (o el id si no tiene documento)."""
    docs = perfil.documentos.all()
    ident = re.sub(r"[^A-Za-z0-9-]", "", docs[0].numero_documento) if docs else ""
    return f"reporte_consumidor_{ident or perfil.pk}_{mes:%Y-%m}.{extension}"


def nombre_archivo_consumidores(filtro: str, mes: date, extension: str) -> str:
    sufijo = "" if filtro == "TODOS" else f"_{filtro.lower()}"
    return f"reporte_consumidores_{mes:%Y-%m}{sufijo}.{extension}"


def cabeceras(filtro: str) -> list[str]:
    cab = [
        "Nombre", "CI", "Municipio", "Solicitudes del mes",
        "Litros despachados", "Cupo usado", "Estado de cuenta",
    ]
    return cab + ["Motivo"] if filtro in FILTROS_ALERTA else cab


def _lineas_encabezado(filtro: str, mes: date) -> list[str]:
    return [f"Mes: {formatear_mes_anio_largo(mes)}", f"Tipo de reporte: {FILTROS[filtro]}"]


def _indicadores(consumidores: list) -> list[tuple[str, int]]:
    from solicitudes.services.validar_cupo import CUPO_MENSUAL_LITROS
    # Calculados sobre la lista ya cargada: sin queries extra.
    return [
        ("Consumidores en el reporte", len(consumidores)),
        ("Solicitudes del mes",        sum(p.solicitudes_mes for p in consumidores)),
        ("Litros despachados",         sum(p.litros_despachados_mes for p in consumidores)),
        ("Con cupo mensual agotado",   sum(1 for p in consumidores if p.cupo_usado_mes >= CUPO_MENSUAL_LITROS)),
    ]


def _contexto(filtro: str, mes: date, consumidores: list, individual: bool):
    """(título, líneas de encabezado, indicadores) del reporte."""
    if individual and consumidores:
        d = fila_consumidor(consumidores[0])
        return (
            f"Reporte del consumidor — {d['nombre']} — {formatear_mes_anio_largo(mes)}",
            [f"Mes: {formatear_mes_anio_largo(mes)}", f"{d['ci']} · {d['municipio']}"],
            [
                ("Solicitudes del mes", d["solicitudes_mes"]),
                ("Litros despachados",  d["litros_despachados"]),
                ("Cupo usado",          d["cupo_texto"]),
                ("Estado de cuenta",    d["estado_cuenta"]),
            ],
        )
    return titulo_reporte(filtro, mes), _lineas_encabezado(filtro, mes), _indicadores(consumidores)


CAB_DETALLE = ["Código", "Fecha", "Combustible", "Litros sol.", "Litros desp.", "Estado", "Estación"]


# ------------------------------------------------
# PDF
# ------------------------------------------------

def _tabla_solicitudes(solicitudes):
    return fmt.tabla(
        CAB_DETALLE,
        [[
            str(s.id_publico)[:8].upper(),
            formatear_fecha(s.fecha_creacion),
            s.get_tipo_combustible_display(),
            f"{s.litros_solicitados} L",
            f"{s.litros_despachados} L" if s.litros_despachados is not None else "—",
            s.get_estado_display(),
            s.estacion_servicio.nombre if s.estacion_servicio else "—",
        ] for s in solicitudes],
        anchos_cm=[2.6, 2.6, 2.8, 2.6, 2.6, 3.0, 10.5],
        numericas=frozenset({3, 4}),
    )


def generar_reporte_pdf(filtro: str, mes: date, incluir_detalle: bool = False,
                        consumidor_id: int | None = None) -> bytes:
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Spacer

    individual = consumidor_id is not None
    if individual:
        filtro, incluir_detalle = "TODOS", True

    consumidores = get_consumidores(filtro, mes, con_solicitudes=incluir_detalle,
                                    consumidor_id=consumidor_id)
    con_motivo   = filtro in FILTROS_ALERTA
    titulo, lineas, crudos = _contexto(filtro, mes, consumidores, individual)

    indicadores = [
        (label, f"{v:,} L".replace(",", ".") if label == "Litros despachados" else str(v))
        for label, v in crudos
    ]

    filas = []
    for p in consumidores:
        d = fila_consumidor(p)
        fila = [d["nombre"], d["ci"], d["municipio"], d["solicitudes_mes"],
                f"{d['litros_despachados']} L", d["cupo_texto"], d["estado_cuenta"]]
        if con_motivo:
            fila.append(d["motivo"])
        filas.append(fila)

    # Anchos: suma = 26.7 cm (ancho útil de la hoja apaisada)
    anchos = ([5.2, 2.9, 3.0, 2.3, 2.6, 2.3, 2.4, 6.0] if con_motivo
              else [7.2, 3.4, 4.2, 2.8, 3.1, 2.8, 3.2])

    # Individual: el recuadro y el encabezado ya tienen sus datos, así
    # que va directo a la tabla de sus solicitudes (sin la tabla de una
    # sola fila ni el encabezado de bloque repetido).
    if individual:
        elementos = [fmt.recuadro_resumen(indicadores), fmt.nota(NOTA_DEFINICIONES)]
        if consumidores and consumidores[0].solicitudes_del_mes:
            elementos += [
                fmt.subtitulo("Solicitudes del mes"),
                _tabla_solicitudes(consumidores[0].solicitudes_del_mes),
            ]
        return fmt.construir_pdf(titulo, lineas, elementos)

    elementos = [
        fmt.recuadro_resumen(indicadores),
        fmt.subtitulo("Consumidores"),
        fmt.tabla(cabeceras(filtro), filas, anchos, numericas=frozenset({3, 4, 5})),
        fmt.nota(NOTA_DEFINICIONES),
    ]

    if incluir_detalle:
        con_solicitudes = [p for p in consumidores if p.solicitudes_del_mes]
        if con_solicitudes:
            elementos.append(fmt.subtitulo("Detalle de solicitudes por consumidor"))
        for p in con_solicitudes:
            d = fila_consumidor(p)
            tabla_sol = _tabla_solicitudes(p.solicitudes_del_mes)
            # Una subsección no se parte entre páginas si entra en una;
            # si es más larga que una página, KeepTogether la deja fluir.
            elementos.append(KeepTogether([
                fmt.encabezado_bloque(f"{d['nombre']} · {d['ci']} · Cupo usado {d['cupo_texto']}"),
                tabla_sol,
                Spacer(1, 0.3 * cm),
            ]))

    return fmt.construir_pdf(titulo, lineas, elementos)


# ------------------------------------------------
# EXCEL
# ------------------------------------------------

def generar_reporte_excel(filtro: str, mes: date, incluir_detalle: bool = False,
                          consumidor_id: int | None = None) -> bytes:
    individual = consumidor_id is not None
    if individual:
        filtro, incluir_detalle = "TODOS", True

    consumidores = get_consumidores(filtro, mes, con_solicitudes=incluir_detalle,
                                    consumidor_id=consumidor_id)
    con_motivo   = filtro in FILTROS_ALERTA
    titulo, lineas, indicadores = _contexto(filtro, mes, consumidores, individual)

    wb = fmt.nuevo_libro()
    fmt.hoja_resumen(wb, titulo, lineas + [NOTA_DEFINICIONES], indicadores)

    filas = []
    for p in consumidores:
        d = fila_consumidor(p)
        fila = [d["nombre"], d["ci"], d["municipio"], d["solicitudes_mes"],
                d["litros_despachados"], d["cupo_texto"], d["estado_cuenta"]]
        if con_motivo:
            fila.append(d["motivo"])
        filas.append(fila)
    fmt.hoja_tabla(
        wb, "Consumidores", cabeceras(filtro), filas,
        anchos=[32, 18, 18, 12, 14, 12, 16] + ([45] if con_motivo else []),
        formatos={3: fmt.FMT_ENTERO, 4: fmt.FMT_ENTERO},
    )

    if incluir_detalle:
        detalle = []
        for p in consumidores:
            d = fila_consumidor(p)
            for s in p.solicitudes_del_mes:
                detalle.append([
                    d["nombre"], d["ci"],
                    str(s.id_publico)[:8].upper(),
                    s.fecha_creacion,
                    s.get_tipo_combustible_display(),
                    s.litros_solicitados,
                    s.litros_despachados,
                    s.get_estado_display(),
                    s.estacion_servicio.nombre if s.estacion_servicio else None,
                ])
        fmt.hoja_tabla(
            wb, "Detalle", ["Consumidor", "CI"] + CAB_DETALLE, detalle,
            anchos=[30, 16, 12, 17, 12, 11, 12, 13, 28],
            formatos={3: fmt.FMT_FECHA_HORA, 5: fmt.FMT_ENTERO, 6: fmt.FMT_ENTERO},
        )

    return fmt.libro_a_bytes(wb)
