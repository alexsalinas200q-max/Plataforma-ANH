# apps/solicitudes/views_reportes.py

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from django.http import HttpResponse

from users.permissions import IsAdminOrANH


class ReporteConsumidoresView(APIView):
    """
    Genera y descarga reportes de consumidores en PDF o Excel.

    Parámetros GET:
      - filtro  : BLOQUEADOS | EN_REVISION | SUPERARON_LIMITE | TODOS
      - formato : PDF | EXCEL (default: EXCEL)
      - dias    : período en días (default: 30)

    Ejemplo:
      GET /api/reportes/consumidores/?filtro=BLOQUEADOS&formato=PDF
      GET /api/reportes/consumidores/?filtro=SUPERARON_LIMITE&dias=30&formato=EXCEL
    """

    permission_classes = [IsAuthenticated, IsAdminOrANH]

    FILTROS_VALIDOS  = ["BLOQUEADOS", "EN_REVISION", "SUPERARON_LIMITE", "TODOS"]
    FORMATOS_VALIDOS = ["PDF", "EXCEL"]

    def get(self, request):

        filtro  = request.query_params.get("filtro",  "TODOS").upper()
        formato = request.query_params.get("formato", "EXCEL").upper()
        dias    = request.query_params.get("dias",    30)

        # Validar filtro
        if filtro not in self.FILTROS_VALIDOS:
            return Response(
                {
                    "detail": f"Filtro inválido. Opciones: {', '.join(self.FILTROS_VALIDOS)}"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar formato
        if formato not in self.FORMATOS_VALIDOS:
            return Response(
                {
                    "detail": f"Formato inválido. Opciones: {', '.join(self.FORMATOS_VALIDOS)}"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar días
        try:
            dias = int(dias)
            if dias < 1 or dias > 365:
                raise ValueError
        except ValueError:
            return Response(
                {"detail": "El parámetro 'dias' debe ser un número entre 1 y 365."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from .services.generar_reportes import (
            generar_reporte_pdf,
            generar_reporte_excel,
        )

        from django.utils import timezone
        fecha_str = timezone.localtime().strftime("%Y%m%d_%H%M")
        nombre    = f"reporte_ANH_{filtro}_{fecha_str}"

        if formato == "PDF":
            contenido      = generar_reporte_pdf(filtro, dias)
            content_type   = "application/pdf"
            nombre_archivo = f"{nombre}.pdf"
        else:
            contenido      = generar_reporte_excel(filtro, dias)
            content_type   = (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )
            nombre_archivo = f"{nombre}.xlsx"

        response = HttpResponse(contenido, content_type=content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{nombre_archivo}"'
        )
        return response