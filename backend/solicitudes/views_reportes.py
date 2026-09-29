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
      - consumidor_id   : <id de ConsumidorPerfil> (opcional). Reporte de
                          un solo consumidor, siempre con detalle; ignora
                          filtro e incluir_detalle. 404 si no existe.

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
            get_consumidores, nombre_archivo_consumidor, nombre_archivo_consumidores,
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

        consumidor_id = None
        if request.query_params.get("consumidor_id"):
            from consumidores.models import ConsumidorPerfil
            try:
                consumidor_id = int(request.query_params["consumidor_id"])
            except ValueError:
                return Response({"detail": "consumidor_id inválido."}, status=status.HTTP_400_BAD_REQUEST)
            if not ConsumidorPerfil.objects.filter(pk=consumidor_id).exists():
                return Response({"detail": "Consumidor no encontrado."}, status=status.HTTP_404_NOT_FOUND)
            filtro, incluir_detalle = "TODOS", True

        encontrados = get_consumidores(filtro, mes, consumidor_id=consumidor_id)
        if consumidor_id is not None:
            if not encontrados[0].solicitudes_mes:
                return Response(
                    {"detail": "El consumidor no tiene solicitudes en el mes seleccionado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif not encontrados:
            return Response(
                {"detail": "No hay consumidores para el tipo de reporte y el mes seleccionados."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        extension = "pdf" if formato == "PDF" else "xlsx"
        nombre_archivo = (
            nombre_archivo_consumidor(encontrados[0], mes, extension) if consumidor_id is not None
            else nombre_archivo_consumidores(filtro, mes, extension)
        )

        if formato == "PDF":
            contenido    = generar_reporte_pdf(filtro, mes, incluir_detalle, consumidor_id)
            content_type = "application/pdf"
        else:
            contenido    = generar_reporte_excel(filtro, mes, incluir_detalle, consumidor_id)
            content_type = (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )

        response = HttpResponse(contenido, content_type=content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{nombre_archivo}"'
        )
        return response
