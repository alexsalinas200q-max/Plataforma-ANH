# apps/solicitudes/views_dashboard.py

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta

from core.fechas import (
    formatear_dia_mes, formatear_fecha_hora, inicio_dia_local,
)
from users.permissions import IsAdminOrANH
from .models import Solicitud


class DashboardANHView(APIView):
    """
    Dashboard de estadísticas en tiempo real para ANH.

    GET /api/dashboard/
    """

    permission_classes = [IsAuthenticated, IsAdminOrANH]

    def get(self, request):

        # Corrige solicitudes vencidas antes de calcular las cifras
        # (ver solicitudes/services/expirar_solicitudes.py).
        from .services.expirar_solicitudes import expirar_solicitudes_vencidas_seguro
        expirar_solicitudes_vencidas_seguro()

        # "Hoy" y "mes" arrancan en la medianoche LOCAL. Con
        # timezone.now().replace(hour=0) arrancaban en la medianoche
        # UTC, que en La Paz son las 20:00 del día anterior.
        ahora         = timezone.now()
        hoy           = timezone.localdate()
        inicio_mes    = inicio_dia_local(hoy.replace(day=1))
        inicio_semana = ahora - timedelta(days=7)
        inicio_hoy    = inicio_dia_local(hoy)

        # ------------------------------------------------
        # SOLICITUDES POR ESTADO
        # ------------------------------------------------

        por_estado = Solicitud.objects.values("estado").annotate(
            total=Count("id")
        ).order_by("estado")

        estados = {
            item["estado"]: item["total"]
            for item in por_estado
        }

        # ------------------------------------------------
        # SOLICITUDES DEL MES
        # ------------------------------------------------

        solicitudes_mes = Solicitud.objects.filter(
            fecha_creacion__gte=inicio_mes
        )

        totales_mes = solicitudes_mes.aggregate(
            total_solicitudes    = Count("id"),
            total_litros_sol     = Sum("litros_solicitados"),
            total_litros_apr     = Sum("litros_aprobados"),
            total_litros_des     = Sum("litros_despachados"),
        )

        # ------------------------------------------------
        # SOLICITUDES DE HOY
        # ------------------------------------------------

        solicitudes_hoy = Solicitud.objects.filter(
            fecha_creacion__gte=inicio_hoy
        ).count()

        despachos_hoy = Solicitud.objects.filter(
            estado="DESPACHADA",
            fecha_despacho__gte=inicio_hoy
        ).count()

        # ------------------------------------------------
        # CONSUMIDORES
        # ------------------------------------------------

        from consumidores.models import ConsumidorPerfil

        consumidores_stats = ConsumidorPerfil.objects.aggregate(
            total                = Count("id"),
            verificados          = Count("id", filter=Q(estado_identidad="VERIFICADO")),
            pendientes_identidad = Count("id", filter=Q(estado_identidad="PENDIENTE")),
            en_revision          = Count("id", filter=Q(estado_identidad="EN_REVISION")),
            bloqueados           = Count("id", filter=Q(alerta_repetitividad="BLOQUEADO")),
            en_revision_alerta   = Count("id", filter=Q(alerta_repetitividad="EN_REVISION")),
        )

        # ------------------------------------------------
        # POR TIPO DE COMBUSTIBLE (mes actual)
        # ------------------------------------------------

        por_combustible = Solicitud.objects.filter(
            fecha_creacion__gte=inicio_mes,
            estado__in=["APROBADA", "DESPACHADA"]
        ).values("tipo_combustible_aprobado").annotate(
            total_solicitudes = Count("id"),
            total_litros      = Sum("litros_aprobados"),
        ).order_by("-total_litros")

        # ------------------------------------------------
        # TOP ESTACIONES POR DESPACHO (mes actual)
        # ------------------------------------------------

        top_estaciones = Solicitud.objects.filter(
            estado="DESPACHADA",
            fecha_despacho__gte=inicio_mes,
            estacion_servicio__isnull=False
        ).values(
            "estacion_servicio__nombre",
            "estacion_servicio__municipio"
        ).annotate(
            total_despachos = Count("id"),
            total_litros    = Sum("litros_despachados"),
        ).order_by("-total_litros")[:5]

        # ------------------------------------------------
        # SOLICITUDES PRÓXIMAS A EXPIRAR (próximas 24h)
        # ------------------------------------------------

        from configuracion.models import ConfiguracionSistema
        config = ConfiguracionSistema.obtener()

        proximas_expirar = Solicitud.objects.filter(
            estado="APROBADA",
            fecha_expiracion__gte=ahora,
            fecha_expiracion__lte=ahora + timedelta(
                hours=config.horas_aviso_expiracion_solicitud
            )
        ).count()

        # ------------------------------------------------
        # TENDENCIA ÚLTIMOS 7 DÍAS
        # ------------------------------------------------

        tendencia = []
        for i in range(6, -1, -1):
            dia        = hoy - timedelta(days=i)
            inicio_dia = inicio_dia_local(dia)
            # __lt contra la medianoche siguiente: sin el hueco del
            # último segundo que dejaba el antiguo 23:59:59.
            fin_dia    = inicio_dia_local(dia + timedelta(days=1))

            solicitudes_dia = Solicitud.objects.filter(
                fecha_creacion__gte=inicio_dia,
                fecha_creacion__lt=fin_dia
            ).count()

            despachos_dia = Solicitud.objects.filter(
                estado="DESPACHADA",
                fecha_despacho__gte=inicio_dia,
                fecha_despacho__lt=fin_dia
            ).count()

            tendencia.append({
                "fecha":       formatear_dia_mes(dia),
                "solicitudes": solicitudes_dia,
                "despachos":   despachos_dia,
            })

        # ------------------------------------------------
        # RESPUESTA
        # ------------------------------------------------

        return Response({

            "generado_en": formatear_fecha_hora(ahora),

            "solicitudes": {
                "por_estado": {
                    "pendientes":  estados.get("PENDIENTE",  0),
                    "observadas":  estados.get("OBSERVADA",  0),
                    "aprobadas":   estados.get("APROBADA",   0),
                    "despachadas": estados.get("DESPACHADA", 0),
                    "rechazadas":  estados.get("RECHAZADA",  0),
                    "canceladas":  estados.get("CANCELADA",  0),
                    "expiradas":   estados.get("EXPIRADA",   0),
                },
                "hoy": {
                    "nuevas":    solicitudes_hoy,
                    "despachos": despachos_hoy,
                },
                "mes_actual": {
                    "total":             totales_mes["total_solicitudes"]    or 0,
                    "litros_solicitados": totales_mes["total_litros_sol"]    or 0,
                    "litros_aprobados":  totales_mes["total_litros_apr"]     or 0,
                    "litros_despachados": totales_mes["total_litros_des"]    or 0,
                },
                "proximas_a_expirar": proximas_expirar,
            },

            "consumidores": {
                "total":                consumidores_stats["total"]                or 0,
                "verificados":          consumidores_stats["verificados"]          or 0,
                "pendientes_identidad": consumidores_stats["pendientes_identidad"] or 0,
                "en_revision_identidad": consumidores_stats["en_revision"]         or 0,
                "bloqueados":           consumidores_stats["bloqueados"]           or 0,
                "en_revision_alerta":   consumidores_stats["en_revision_alerta"]   or 0,
            },

            "por_combustible": [
                {
                    "tipo":     item["tipo_combustible_aprobado"] or "—",
                    "solicitudes": item["total_solicitudes"],
                    "litros":   item["total_litros"] or 0,
                }
                for item in por_combustible
            ],

            "top_estaciones": [
                {
                    "nombre":   item["estacion_servicio__nombre"],
                    "municipio": item["estacion_servicio__municipio"],
                    "despachos": item["total_despachos"],
                    "litros":   item["total_litros"] or 0,
                }
                for item in top_estaciones
            ],

            "tendencia_7_dias": tendencia,
        })