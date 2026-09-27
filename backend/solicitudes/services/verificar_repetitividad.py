# apps/solicitudes/services/verificar_repetitividad.py
#
# DEPRECATED: reemplazado parcialmente por validar_cupo.py (regla mensual bloqueante).
# Las 3 reglas restantes (semanal, cantidad/30 días, rotación de estaciones)
# quedan documentadas como trabajo futuro para módulo de alertas al ANH.
#
# Ya no se llama desde ningún punto del código (antes se llamaba desde
# despachar_solicitud.py). Se deja el archivo sin borrar para no perder
# la lógica de las 3 reglas pendientes de refactor.

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def verificar_repetitividad(solicitud) -> dict:
    """
    Verifica si el consumidor supera los límites configurados
    tras un despacho. Se llama automáticamente desde
    despachar_solicitud.

    Controles realizados:
    1. Número de solicitudes APROBADAS/DESPACHADAS en el período
    2. Litros acumulados en el mes
    3. Litros acumulados en la semana
    4. Rotación de estaciones distintas en el mes

    Retorna un dict con el resultado del análisis.
    """
    from configuracion.models import ConfiguracionSistema
    from consumidores.models import ConsumidorPerfil
    from solicitudes.models import Solicitud

    config     = ConfiguracionSistema.obtener()
    consumidor = solicitud.consumidor
    ahora      = timezone.now()

    # ------------------------------------------------
    # PERÍODOS DE ANÁLISIS
    # ------------------------------------------------

    inicio_periodo = ahora - timedelta(days=config.periodo_control_solicitudes_dias)
    inicio_mes     = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    inicio_semana  = ahora - timedelta(days=7)

    # ------------------------------------------------
    # SOLICITUDES EN EL PERÍODO
    # ------------------------------------------------

    solicitudes_periodo = Solicitud.objects.filter(
        consumidor=consumidor,
        estado__in=["APROBADA", "DESPACHADA"],
        fecha_creacion__gte=inicio_periodo
    )

    total_solicitudes_periodo = solicitudes_periodo.count()

    # ------------------------------------------------
    # LITROS ACUMULADOS
    # ------------------------------------------------

    from django.db.models import Sum

    litros_mes = Solicitud.objects.filter(
        consumidor=consumidor,
        estado="DESPACHADA",
        fecha_despacho__gte=inicio_mes
    ).aggregate(total=Sum("litros_despachados"))["total"] or 0

    litros_semana = Solicitud.objects.filter(
        consumidor=consumidor,
        estado="DESPACHADA",
        fecha_despacho__gte=inicio_semana
    ).aggregate(total=Sum("litros_despachados"))["total"] or 0

    # ------------------------------------------------
    # ROTACIÓN DE ESTACIONES
    # ------------------------------------------------

    estaciones_mes = Solicitud.objects.filter(
        consumidor=consumidor,
        estado="DESPACHADA",
        fecha_despacho__gte=inicio_mes
    ).values("estacion_servicio").distinct().count()

    # ------------------------------------------------
    # EVALUACIÓN DE ALERTAS
    # ------------------------------------------------

    alertas = []

    if total_solicitudes_periodo >= config.limite_solicitudes_por_periodo:
        alertas.append(
            f"Superó el límite de {config.limite_solicitudes_por_periodo} "
            f"solicitudes en {config.periodo_control_solicitudes_dias} días "
            f"({total_solicitudes_periodo} solicitudes)."
        )

    if litros_mes > config.limite_litros_mensual:
        alertas.append(
            f"Superó el límite mensual de {config.limite_litros_mensual}L "
            f"(acumuló {litros_mes}L este mes)."
        )

    if config.limite_litros_semanal > 0 and litros_semana > config.limite_litros_semanal:
        alertas.append(
            f"Superó el límite semanal de {config.limite_litros_semanal}L "
            f"(acumuló {litros_semana}L esta semana)."
        )

    if estaciones_mes > config.max_estaciones_distintas_por_mes:
        alertas.append(
            f"Retiró en {estaciones_mes} estaciones distintas este mes "
            f"(máximo permitido: {config.max_estaciones_distintas_por_mes})."
        )

    # ------------------------------------------------
    # APLICAR ALERTA SI CORRESPONDE
    # ------------------------------------------------

    resultado = {
        "total_solicitudes_periodo": total_solicitudes_periodo,
        "litros_mes":                litros_mes,
        "litros_semana":             litros_semana,
        "estaciones_mes":            estaciones_mes,
        "alertas":                   alertas,
        "alerta_activada":           len(alertas) > 0,
    }

    if alertas:
        motivo = " | ".join(alertas)
        _aplicar_alerta(consumidor, motivo)
        resultado["motivo"] = motivo
        logger.warning(
            f"Alerta de repetitividad activada para consumidor "
            f"{consumidor.user.email}: {motivo}"
        )

    return resultado


def _aplicar_alerta(consumidor, motivo: str) -> None:
    """
    Marca al consumidor EN_REVISION y notifica a ANH por email.
    Solo aplica si no está ya BLOQUEADO.
    """
    from consumidores.models import ConsumidorPerfil
    from users.email_service import _enviar_email
    from django.conf import settings

    # No sobreescribir un BLOQUEADO con EN_REVISION
    if consumidor.alerta_repetitividad == ConsumidorPerfil.EstadoAlerta.BLOQUEADO:
        return

    consumidor.alerta_repetitividad = ConsumidorPerfil.EstadoAlerta.EN_REVISION
    consumidor.fecha_alerta          = timezone.now()
    consumidor.motivo_bloqueo        = motivo
    consumidor.save(update_fields=[
        "alerta_repetitividad",
        "fecha_alerta",
        "motivo_bloqueo",
        "fecha_actualizacion"
    ])

    # Notificar al consumidor
    _enviar_email(
        asunto="Cuenta en revisión — ANH",
        mensaje=(
            f"Hola {consumidor.user.nombres},\n\n"
            f"Su cuenta ha sido marcada para revisión por la ANH "
            f"debido a actividad inusual:\n\n"
            f"{motivo}\n\n"
            f"Comuníquese con la ANH para más información.\n\n"
            f"Agencia Nacional de Hidrocarburos\nBolivia"
        ),
        destinatario=consumidor.user.email
    )

    # Notificar a ANH por email
    anh_email = getattr(settings, "ANH_NOTIFICACIONES_EMAIL", "")
    if anh_email:
        _enviar_email(
            asunto=f"⚠️ Alerta de repetitividad — {consumidor.user.nombre_completo()}",
            mensaje=(
                f"Se ha activado una alerta de repetitividad:\n\n"
                f"Consumidor: {consumidor.user.nombre_completo()}\n"
                f"Email: {consumidor.user.email}\n"
                f"CI: {consumidor.documentos.first().numero_documento if consumidor.documentos.exists() else 'Sin documento'}\n\n"
                f"Motivo: {motivo}\n\n"
                f"Ingrese al sistema para revisar el caso."
            ),
            destinatario=anh_email
        )