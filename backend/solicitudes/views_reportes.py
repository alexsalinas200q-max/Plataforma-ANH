# apps/solicitudes/views_reportes.py

from datetime import date

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.http import HttpResponse
from django.utils import timezone

from users.permissions import IsAdminOrANH


class ReporteConsumidoresView(APIView):
    """
    Genera y descarga el reporte de consumidores de un mes, en PDF o Excel.

    Parámetros GET:
      - filtro          : TODOS | CUPO_AGOTADO | BLOQUEADOS | EN_REVISION
                          (default: TODOS)
      - mes             : AAAA-MM (default: mes actual, hora local)
      - formato         : PDF | EXCEL (default: EXCEL)
      - incluir_detalle : true | false (default: false). Agrega las
                          solicitudes del mes de cada consumidor.

    400 si algún parámetro es inválido o si el filtro no tiene
    consumidores (no se generan archivos vacíos).

    Ejemplo:
      GET /api/reportes/consumidores/?filtro=CUPO_AGOTADO&mes=2026-09&formato=PDF
    """

    permission_classes = [IsAuthenticated, IsAdminOrANH]

    FORMATOS_VALIDOS = ["PDF", "EXCEL"]

    def get(self, request):
        from .services.generar_reportes import (
            FILTROS, generar_reporte_excel, generar_reporte_pdf,
            get_consumidores, nombre_archivo_consumidores,
        )

        filtro  = request.query_params.get("filtro",  "TODOS").upper()
        formato = request.query_params.get("formato", "EXCEL").upper()

        if filtro not in FILTROS:
            return Response(
                {"detail": f"Filtro inválido. Opciones: {', '.join(FILTROS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if formato not in self.FORMATOS_VALIDOS:
            return Response(
                {"detail": f"Formato inválido. Opciones: {', '.join(self.FORMATOS_VALIDOS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mes_param = request.query_params.get("mes")
        if mes_param:
            try:
                mes = date.fromisoformat(f"{mes_param}-01")
            except ValueError:
                return Response(
                    {"detail": "Mes inválido. Usa el formato AAAA-MM."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            mes = timezone.localdate().replace(day=1)

        incluir_detalle = request.query_params.get("incluir_detalle", "").lower() in ("1", "true", "si", "sí")

        if not get_consumidores(filtro, mes):
            return Response(
                {"detail": "No hay consumidores para el tipo de reporte y el mes seleccionados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if formato == "PDF":
            contenido      = generar_reporte_pdf(filtro, mes, incluir_detalle)
            content_type   = "application/pdf"
            nombre_archivo = nombre_archivo_consumidores(filtro, mes, "pdf")
        else:
            contenido      = generar_reporte_excel(filtro, mes, incluir_detalle)
            content_type   = (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )
            nombre_archivo = nombre_archivo_consumidores(filtro, mes, "xlsx")

        response = HttpResponse(contenido, content_type=content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{nombre_archivo}"'
        )
        return response
