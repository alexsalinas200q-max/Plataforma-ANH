# apps/solicitudes/views_estadisticas.py
#
# Módulo de Reportes, pestaña Solicitudes.
#
# Definiciones (aprobadas alguna vez, resueltas, tasas, período por
# fecha de creación): ver solicitudes/services/estadisticas.py.

from datetime import date, datetime, timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.fechas import formatear_dia_mes, formatear_mes_anio
from users.permissions import IsAdminOrANH
from .models import Solicitud
from .services.estadisticas import (
    SIN_DATOS, calcular_indicadores, filtros_desde_params,
    solicitudes_filtradas, texto_periodo,
)


# Rangos de hasta este largo se agrupan por día; más largos, por mes.
MAX_DIAS_AGRUPACION_DIARIA = 31

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

        filtros = filtros_desde_params(request.query_params)
        desde, hasta = filtros["desde"], filtros["hasta"]
        qs = solicitudes_filtradas(filtros)

        E = Solicitud.EstadoSolicitud
        despachadas = qs.filter(estado=E.DESPACHADA)
        indicadores = calcular_indicadores(qs)

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
            **indicadores,
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

        formato = request.query_params.get("formato", "EXCEL").upper()

        filtros = filtros_desde_params(request.query_params)
        if not solicitudes_filtradas(filtros).exists():
            raise ValidationError({"detail": SIN_DATOS})

        from .services.generar_reportes_solicitudes import (
            generar_excel_solicitudes,
            generar_pdf_solicitudes,
            nombre_archivo_solicitudes,
        )

        if formato == "PDF":
            contenido    = generar_pdf_solicitudes(filtros)
            content_type = "application/pdf"
            archivo      = nombre_archivo_solicitudes(filtros, "pdf")
        else:
            contenido    = generar_excel_solicitudes(filtros)
            content_type = (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )
            archivo = nombre_archivo_solicitudes(filtros, "xlsx")

        response = HttpResponse(contenido, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{archivo}"'
        return response
