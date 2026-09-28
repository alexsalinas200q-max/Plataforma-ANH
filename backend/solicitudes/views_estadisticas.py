# apps/solicitudes/views_estadisticas.py

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta

from core.fechas import formatear_mes_anio
from users.permissions import IsAdminOrANH
from .models import Solicitud


class EstadisticasSolicitudesView(APIView):
    """
    Retorna estadísticas de solicitudes para el módulo de Reportes.

    Parámetros GET opcionales:
      - fecha_desde : YYYY-MM-DD
      - fecha_hasta : YYYY-MM-DD
      - estado      : PENDIENTE | APROBADA | DESPACHADA | ...
      - combustible : GASOLINA | DIESEL
      - estacion    : <id>
    """

    permission_classes = [IsAuthenticated, IsAdminOrANH]

    def get(self, request):
        # Corrige solicitudes vencidas antes de calcular las cifras
        # (ver solicitudes/services/expirar_solicitudes.py).
        from .services.expirar_solicitudes import expirar_solicitudes_vencidas_seguro
        expirar_solicitudes_vencidas_seguro()

        # ------------------------------------------------
        # FILTROS
        # ------------------------------------------------
        fecha_desde  = request.query_params.get("fecha_desde")
        fecha_hasta  = request.query_params.get("fecha_hasta")
        estado       = request.query_params.get("estado")
        combustible  = request.query_params.get("combustible")
        estacion_id  = request.query_params.get("estacion")

        qs = Solicitud.objects.all()

        if fecha_desde:
            qs = qs.filter(fecha_creacion__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_creacion__date__lte=fecha_hasta)
        if estado:
            qs = qs.filter(estado=estado)
        if combustible:
            qs = qs.filter(tipo_combustible=combustible)
        if estacion_id:
            qs = qs.filter(estacion_servicio_id=estacion_id)

        # ------------------------------------------------
        # 1. RESUMEN GENERAL
        # ------------------------------------------------
        total = qs.count()
        totales_litros = qs.aggregate(
            litros_solicitados=Sum("litros_solicitados"),
            litros_aprobados=Sum("litros_aprobados"),
            litros_despachados=Sum("litros_despachados"),
        )

        # ------------------------------------------------
        # 2. POR ESTADO
        # ------------------------------------------------
        por_estado = list(
            qs.values("estado")
              .annotate(total=Count("id"))
              .order_by("-total")
        )

        # ------------------------------------------------
        # 3. POR TIPO DE COMBUSTIBLE
        # ------------------------------------------------
        por_combustible = list(
            qs.values("tipo_combustible")
              .annotate(
                  total=Count("id"),
                  litros=Sum("litros_solicitados"),
              )
              .order_by("-total")
        )

        # ------------------------------------------------
        # 4. POR ESTACIÓN DE SERVICIO (top 10)
        # ------------------------------------------------
        por_estacion = list(
            qs.filter(estacion_servicio__isnull=False)
              .values(
                  "estacion_servicio__id",
                  "estacion_servicio__nombre",
              )
              .annotate(
                  total=Count("id"),
                  litros_despachados=Sum("litros_despachados"),
              )
              .order_by("-total")[:10]
        )

        por_estacion_fmt = [
            {
                "estacion_id":    e["estacion_servicio__id"],
                "estacion_nombre": e["estacion_servicio__nombre"],
                "total":          e["total"],
                "litros_despachados": e["litros_despachados"] or 0,
            }
            for e in por_estacion
        ]

        # ------------------------------------------------
        # 5. EVOLUCIÓN MENSUAL (últimos 12 meses)
        # ------------------------------------------------
        from django.db.models.functions import TruncMonth
        doce_meses = timezone.now() - timedelta(days=365)

        por_mes = list(
            qs.filter(fecha_creacion__gte=doce_meses)
              .annotate(mes=TruncMonth("fecha_creacion"))
              .values("mes")
              .annotate(
                  total=Count("id"),
                  aprobadas=Count("id", filter=Q(estado="APROBADA")),
                  despachadas=Count("id", filter=Q(estado="DESPACHADA")),
                  litros=Sum("litros_solicitados"),
              )
              .order_by("mes")
        )

        por_mes_fmt = [
            {
                "mes":        formatear_mes_anio(m["mes"]),
                "total":      m["total"],
                "aprobadas":  m["aprobadas"],
                "despachadas": m["despachadas"],
                "litros":     m["litros"] or 0,
            }
            for m in por_mes
        ]

        # ------------------------------------------------
        # 6. POR MUNICIPIO (top 10)
        # ------------------------------------------------
        por_municipio = list(
            qs.filter(municipio__isnull=False)
              .values("municipio__nombre")
              .annotate(total=Count("id"))
              .order_by("-total")[:10]
        )

        por_municipio_fmt = [
            {
                "municipio": m["municipio__nombre"],
                "total":     m["total"],
            }
            for m in por_municipio
        ]

        return Response({
            "total":          total,
            "litros": {
                "solicitados":  totales_litros["litros_solicitados"] or 0,
                "aprobados":    totales_litros["litros_aprobados"]   or 0,
                "despachados":  totales_litros["litros_despachados"] or 0,
            },
            "por_estado":      por_estado,
            "por_combustible": por_combustible,
            "por_estacion":    por_estacion_fmt,
            "por_mes":         por_mes_fmt,
            "por_municipio":   por_municipio_fmt,
        })


# ------------------------------------------------
# REPORTE DESCARGABLE DE SOLICITUDES
# ------------------------------------------------

class ReporteSolicitudesView(APIView):
    """
    Genera y descarga reportes de solicitudes en PDF o Excel.

    Parámetros GET:
      - formato     : PDF | EXCEL (default: EXCEL)
      - fecha_desde : YYYY-MM-DD
      - fecha_hasta : YYYY-MM-DD
      - estado      : filtro de estado
      - combustible : GASOLINA | DIESEL
      - estacion    : <id>
    """

    permission_classes = [IsAuthenticated, IsAdminOrANH]

    def get(self, request):
        # Corrige solicitudes vencidas antes de generar el reporte
        # (ver solicitudes/services/expirar_solicitudes.py).
        from .services.expirar_solicitudes import expirar_solicitudes_vencidas_seguro
        expirar_solicitudes_vencidas_seguro()

        from django.http import HttpResponse

        formato     = request.query_params.get("formato", "EXCEL").upper()
        fecha_desde = request.query_params.get("fecha_desde")
        fecha_hasta = request.query_params.get("fecha_hasta")
        estado      = request.query_params.get("estado")
        combustible = request.query_params.get("combustible")
        estacion_id = request.query_params.get("estacion")

        filtros = {
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "estado":      estado,
            "combustible": combustible,
            "estacion_id": estacion_id,
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