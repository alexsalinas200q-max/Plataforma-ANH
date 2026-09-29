# apps/solicitudes/views_estadisticas.py
#
# Módulo de Reportes, pestaña Solicitudes.
#
# Definiciones (usadas en pantalla y en los archivos):
#   - Aprobada alguna vez = fecha_aprobacion no nula (incluye DESPACHADA
#     y EXPIRADA, no solo las que siguen en estado APROBADA).
#   - Resueltas = aprobadas alguna vez + RECHAZADAS.
#   - Tasa de aprobación = aprobadas alguna vez / resueltas; tasa de
#     rechazo = RECHAZADAS / resueltas. None si resueltas = 0.
#   - El período filtra por FECHA DE CREACIÓN ("Solicitudes creadas
#     entre X y Y"), en hora local. Por defecto, el mes actual.
#   - La medida principal es litros despachados (subsidio entregado).

from datetime import date, datetime, timedelta

from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.fechas import formatear_dia_mes, formatear_fecha, formatear_mes_anio
from users.permissions import IsAdminOrANH
from .models import Solicitud


# Rangos de hasta este largo se agrupan por día; más largos, por mes.
MAX_DIAS_AGRUPACION_DIARIA = 31

SIN_DATOS = "No hay solicitudes en el rango seleccionado."


# ------------------------------------------------
# PERÍODO Y FILTROS (compartido con ReporteSolicitudesView)
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


def texto_periodo(desde: date, hasta: date) -> str:
    return f"Solicitudes creadas entre {formatear_fecha(desde)} y {formatear_fecha(hasta)}"


def solicitudes_filtradas(params, desde: date, hasta: date):
    qs = Solicitud.objects.filter(
        fecha_creacion__date__gte=desde,
        fecha_creacion__date__lte=hasta,
    )
    if params.get("estado"):
        qs = qs.filter(estado=params["estado"])
    if params.get("combustible"):
        qs = qs.filter(tipo_combustible=params["combustible"])
    if params.get("estacion"):
        qs = qs.filter(estacion_servicio_id=params["estacion"])
    return qs


def _tasa(parte: int, resueltas: int):
    return round(parte * 100 / resueltas, 1) if resueltas else None


# ------------------------------------------------
# EVOLUCIÓN (por día o por mes, según el largo del rango)
# ------------------------------------------------

def _evolucion(qs, desde: date, hasta: date) -> dict:
    por_dia = (hasta - desde).days + 1 <= MAX_DIAS_AGRUPACION_DIARIA
    trunc   = TruncDate("fecha_creacion") if por_dia else TruncMonth("fecha_creacion")

    filas = (
        qs.annotate(bucket=trunc)
          .values("bucket")
          .annotate(
              creadas=Count("id"),
              aprobadas=Count("id", filter=Q(fecha_aprobacion__isnull=False)),
              despachadas=Count("id", filter=Q(estado=Solicitud.EstadoSolicitud.DESPACHADA)),
          )
    )
    datos = {}
    for f in filas:
        clave = f["bucket"]
        if not por_dia:
            # TruncMonth devuelve un datetime aware (medianoche local del
            # 1° del mes): se pasa a date para cruzarlo con la serie.
            if isinstance(clave, datetime):
                clave = timezone.localtime(clave).date() if timezone.is_aware(clave) else clave.date()
            clave = clave.replace(day=1)
        datos[clave] = f

    # Serie completa (días o meses sin solicitudes en 0) para que el
    # gráfico no salte períodos.
    puntos = []
    if por_dia:
        dia = desde
        while dia <= hasta:
            puntos.append((dia, formatear_dia_mes(dia)))
            dia += timedelta(days=1)
    else:
        mes = desde.replace(day=1)
        while mes <= hasta:
            puntos.append((mes, formatear_mes_anio(mes)))
            mes = (mes.replace(day=28) + timedelta(days=4)).replace(day=1)

    return {
        "agrupacion": "dia" if por_dia else "mes",
        "puntos": [
            {
                "etiqueta":    etiqueta,
                "creadas":     datos.get(clave, {}).get("creadas", 0),
                "aprobadas":   datos.get(clave, {}).get("aprobadas", 0),
                "despachadas": datos.get(clave, {}).get("despachadas", 0),
            }
            for clave, etiqueta in puntos
        ],
    }


# ------------------------------------------------
# ESTADÍSTICAS
# ------------------------------------------------

class EstadisticasSolicitudesView(APIView):
    """
    GET /api/estadisticas/solicitudes/

    Parámetros opcionales: fecha_desde, fecha_hasta (AAAA-MM-DD; por
    defecto el mes actual), estado, combustible, estacion (<id>).
    Un rango sin solicitudes responde 200 con total 0.
    """

    permission_classes = [IsAuthenticated, IsAdminOrANH]

    def get(self, request):
        # Corrige solicitudes vencidas antes de calcular las cifras
        # (ver solicitudes/services/expirar_solicitudes.py).
        from .services.expirar_solicitudes import expirar_solicitudes_vencidas_seguro
        expirar_solicitudes_vencidas_seguro()

        desde, hasta = resolver_periodo(request.query_params)
        qs = solicitudes_filtradas(request.query_params, desde, hasta)

        E = Solicitud.EstadoSolicitud
        despachadas = qs.filter(estado=E.DESPACHADA)
        cero = Value(0)

        resumen = qs.aggregate(
            total=Count("id"),
            aprobadas=Count("id", filter=Q(fecha_aprobacion__isnull=False)),
            rechazadas=Count("id", filter=Q(estado=E.RECHAZADA)),
            litros_despachados=Coalesce(
                Sum("litros_despachados", filter=Q(estado=E.DESPACHADA)), cero,
            ),
        )
        resueltas = resumen["aprobadas"] + resumen["rechazadas"]

        por_estado = list(
            qs.values("estado").annotate(total=Count("id")).order_by("-total")
        )

        # Combustible despachado = el aprobado (puede diferir del pedido)
        combustible = Coalesce("tipo_combustible_aprobado", "tipo_combustible")
        litros_por_tipo = {
            f["tipo"]: f["litros"] or 0
            for f in despachadas.annotate(tipo=combustible)
                                .values("tipo")
                                .annotate(litros=Sum("litros_despachados"))
        }
        despachados_por_combustible = [
            {"tipo": valor, "etiqueta": etiqueta, "litros": litros_por_tipo.get(valor, 0)}
            for valor, etiqueta in Solicitud.TipoCombustible.choices
        ]

        por_estacion = [
            {
                "estacion_id":        e["estacion_servicio__id"],
                "nombre":             e["estacion_servicio__nombre"],
                "litros_despachados": e["litros"] or 0,
                "despachos":          e["despachos"],
            }
            for e in despachadas.filter(estacion_servicio__isnull=False)
                .values("estacion_servicio__id", "estacion_servicio__nombre")
                .annotate(litros=Sum("litros_despachados"), despachos=Count("id"))
                .order_by("-litros")[:10]
        ]

        por_municipio = [
            {"municipio": m["municipio__nombre"], "litros_despachados": m["litros"] or 0}
            for m in despachadas.filter(municipio__isnull=False)
                .values("municipio__nombre")
                .annotate(litros=Sum("litros_despachados"))
                .order_by("-litros")[:10]
        ]

        return Response({
            "periodo": {
                "desde": desde.isoformat(),
                "hasta": hasta.isoformat(),
                "texto": texto_periodo(desde, hasta),
            },
            "total":                resumen["total"],
            "litros_despachados":   resumen["litros_despachados"],
            "aprobadas_alguna_vez": resumen["aprobadas"],
            "rechazadas":           resumen["rechazadas"],
            "resueltas":            resueltas,
            "tasa_aprobacion":      _tasa(resumen["aprobadas"], resueltas),
            "tasa_rechazo":         _tasa(resumen["rechazadas"], resueltas),
            "por_estado":           por_estado,
            "evolucion":            _evolucion(qs, desde, hasta),
            "despachados_por_combustible": despachados_por_combustible,
            "por_estacion":         por_estacion,
            "por_municipio":        por_municipio,
        })


# ------------------------------------------------
# REPORTE DESCARGABLE DE SOLICITUDES
# ------------------------------------------------

class ReporteSolicitudesView(APIView):
    """
    Genera y descarga reportes de solicitudes en PDF o Excel.

    Parámetros GET:
      - formato     : PDF | EXCEL (default: EXCEL)
      - fecha_desde : YYYY-MM-DD (default: 1° del mes actual)
      - fecha_hasta : YYYY-MM-DD (default: hoy)
      - estado      : filtro de estado
      - combustible : GASOLINA | DIESEL
      - estacion    : <id>

    400 si desde > hasta o si el rango no tiene solicitudes (no se
    generan archivos vacíos).
    """

    permission_classes = [IsAuthenticated, IsAdminOrANH]

    def get(self, request):
        # Corrige solicitudes vencidas antes de generar el reporte
        # (ver solicitudes/services/expirar_solicitudes.py).
        from .services.expirar_solicitudes import expirar_solicitudes_vencidas_seguro
        expirar_solicitudes_vencidas_seguro()

        from django.http import HttpResponse

        params  = request.query_params
        formato = params.get("formato", "EXCEL").upper()

        desde, hasta = resolver_periodo(params)
        if not solicitudes_filtradas(params, desde, hasta).exists():
            raise ValidationError({"detail": SIN_DATOS})

        filtros = {
            "fecha_desde": desde.isoformat(),
            "fecha_hasta": hasta.isoformat(),
            "estado":      params.get("estado"),
            "combustible": params.get("combustible"),
            "estacion_id": params.get("estacion"),
        }

        fecha_str = timezone.localtime().strftime("%Y%m%d_%H%M")
        nombre    = f"reporte_solicitudes_{fecha_str}"

        from .services.generar_reportes_solicitudes import (
            generar_excel_solicitudes,
            generar_pdf_solicitudes,
        )

        if formato == "PDF":
            contenido    = generar_pdf_solicitudes(filtros)
            content_type = "application/pdf"
            archivo      = f"{nombre}.pdf"
        else:
            contenido    = generar_excel_solicitudes(filtros)
            content_type = (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )
            archivo = f"{nombre}.xlsx"

        response = HttpResponse(contenido, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{archivo}"'
        return response
