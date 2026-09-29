# apps/solicitudes/services/estadisticas.py
#
# Período, filtros e indicadores de solicitudes, compartidos por la
# pantalla de Reportes (EstadisticasSolicitudesView) y por los archivos
# PDF/Excel (generar_reportes_solicitudes), para que ambos muestren
# exactamente los mismos números.
#
# Definiciones:
#   - Aprobada alguna vez = fecha_aprobacion no nula (incluye DESPACHADA
#     y EXPIRADA, no solo las que siguen en estado APROBADA).
#   - Resueltas = aprobadas alguna vez + RECHAZADAS.
#   - Tasa de aprobación = aprobadas alguna vez / resueltas; tasa de
#     rechazo = RECHAZADAS / resueltas. None si resueltas = 0.
#   - El período filtra por FECHA DE CREACIÓN ("Solicitudes creadas
#     entre X y Y"), en hora local. Por defecto, el mes actual.
#   - La medida principal es litros despachados (subsidio entregado).

from datetime import date

from django.db.models import Count, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.fechas import formatear_fecha


SIN_DATOS = "No hay solicitudes en el rango seleccionado."


# ------------------------------------------------
# PERÍODO Y FILTROS
# ------------------------------------------------

def _parse_fecha(valor: str | None, nombre: str) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise ValidationError({"detail": f"Fecha '{nombre}' inválida. Usa el formato AAAA-MM-DD."})


def resolver_periodo(params) -> tuple[date, date]:
    """
    (desde, hasta) del query string; por defecto el mes actual en hora
    local. 400 si desde > hasta.
    """
    hoy   = timezone.localdate()
    desde = _parse_fecha(params.get("fecha_desde"), "desde") or hoy.replace(day=1)
    hasta = _parse_fecha(params.get("fecha_hasta"), "hasta") or hoy
    if desde > hasta:
        raise ValidationError({"detail": "La fecha 'desde' no puede ser posterior a la fecha 'hasta'."})
    return desde, hasta


def filtros_desde_params(params) -> dict:
    """Filtros normalizados: desde/hasta (date), estado, combustible, estacion."""
    desde, hasta = resolver_periodo(params)
    return {
        "desde":       desde,
        "hasta":       hasta,
        "estado":      params.get("estado") or None,
        "combustible": params.get("combustible") or None,
        "estacion":    params.get("estacion") or None,
    }


def texto_periodo(desde: date, hasta: date) -> str:
    return f"Solicitudes creadas entre {formatear_fecha(desde)} y {formatear_fecha(hasta)}"


def solicitudes_filtradas(filtros: dict):
    from solicitudes.models import Solicitud

    qs = Solicitud.objects.filter(
        fecha_creacion__date__gte=filtros["desde"],
        fecha_creacion__date__lte=filtros["hasta"],
    )
    if filtros.get("estado"):
        qs = qs.filter(estado=filtros["estado"])
    if filtros.get("combustible"):
        qs = qs.filter(tipo_combustible=filtros["combustible"])
    if filtros.get("estacion"):
        qs = qs.filter(estacion_servicio_id=filtros["estacion"])
    return qs


def describir_filtros(filtros: dict) -> list[str]:
    """Filtros aplicados en texto legible (nombres, no códigos ni IDs)."""
    from estaciones.models import EstacionServicio
    from solicitudes.models import Solicitud

    partes = []
    if filtros.get("estado"):
        estados = dict(Solicitud.EstadoSolicitud.choices)
        partes.append(f"Estado: {estados.get(filtros['estado'], filtros['estado'])}")
    if filtros.get("combustible"):
        tipos = dict(Solicitud.TipoCombustible.choices)
        partes.append(f"Combustible: {tipos.get(filtros['combustible'], filtros['combustible'])}")
    if filtros.get("estacion"):
        nombre = (
            EstacionServicio.objects.filter(pk=filtros["estacion"])
            .values_list("nombre", flat=True).first()
        )
        partes.append(f"Estación: {nombre or 'no encontrada'}")
    return partes or ["Sin filtros adicionales"]


# ------------------------------------------------
# INDICADORES
# ------------------------------------------------

def _tasa(parte: int, resueltas: int):
    return round(parte * 100 / resueltas, 1) if resueltas else None


def calcular_indicadores(qs) -> dict:
    from solicitudes.models import Solicitud
    E = Solicitud.EstadoSolicitud

    r = qs.aggregate(
        total=Count("id"),
        aprobadas=Count("id", filter=Q(fecha_aprobacion__isnull=False)),
        rechazadas=Count("id", filter=Q(estado=E.RECHAZADA)),
        litros_despachados=Coalesce(
            Sum("litros_despachados", filter=Q(estado=E.DESPACHADA)),
            Value(0, output_field=IntegerField()),
        ),
    )
    resueltas = r["aprobadas"] + r["rechazadas"]
    return {
        "total":                r["total"],
        "litros_despachados":   r["litros_despachados"],
        "aprobadas_alguna_vez": r["aprobadas"],
        "rechazadas":           r["rechazadas"],
        "resueltas":            resueltas,
        "tasa_aprobacion":      _tasa(r["aprobadas"], resueltas),
        "tasa_rechazo":         _tasa(r["rechazadas"], resueltas),
    }


def resumen_por_estacion(qs) -> list[dict]:
    """
    Despachos por estación: cantidad, litros de Gasolina, de Diésel y
    total. El combustible es el aprobado (el que efectivamente se
    despachó), con el solicitado como respaldo.
    """
    from solicitudes.models import Solicitud
    E = Solicitud.EstadoSolicitud
    T = Solicitud.TipoCombustible
    cero = Value(0, output_field=IntegerField())

    def litros_de(tipo):
        return Coalesce(Sum("litros_despachados", filter=(
            Q(tipo_combustible_aprobado=tipo)
            | Q(tipo_combustible_aprobado__isnull=True, tipo_combustible=tipo)
        )), cero)

    filas = (
        qs.filter(estado=E.DESPACHADA, estacion_servicio__isnull=False)
          .values("estacion_servicio__nombre")
          .annotate(
              despachos=Count("id"),
              gasolina=litros_de(T.GASOLINA),
              diesel=litros_de(T.DIESEL),
              total=Coalesce(Sum("litros_despachados"), cero),
          )
          .order_by("-total", "estacion_servicio__nombre")
    )
    return [
        {
            "estacion":  f["estacion_servicio__nombre"],
            "despachos": f["despachos"],
            "gasolina":  f["gasolina"],
            "diesel":    f["diesel"],
            "total":     f["total"],
        }
        for f in filas
    ]
