# apps/solicitudes/services/expirar_solicitudes.py
#
# Reemplaza a solicitudes/cron.py (borrado: dependía de django-crontab,
# que nunca estuvo instalado ni configurado — no hay demonio cron en
# los contenedores efímeros de Railway que lo dispare). El mecanismo
# real es ejecución perezosa: expirar_solicitudes_vencidas_seguro() se
# llama desde los listados/dashboard/estadísticas (ver solicitudes/
# views.py, views_dashboard.py, views_estadisticas.py) para que las
# solicitudes vencidas se corrijan antes de mostrarse, sin depender de
# ningún proceso programado. En producción, además, un servicio Cron de
# Railway corre el management command `expirar_solicitudes` cada 10
# minutos; la ejecución perezosa queda como respaldo.
#
# Emails: se envían con transaction.on_commit, nunca dentro de la
# transacción que tiene las filas bloqueadas (select_for_update). Así
# una llamada lenta a Brevo (hasta 10 s de timeout) no retiene los
# locks, y si la transacción se revierte no sale ningún email de un
# rechazo que no quedó guardado.

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

MOTIVO_RECHAZO_AUTOMATICO = (
    "Rechazada automáticamente: no se respondió la observación "
    "dentro del plazo."
)


# ------------------------------------------------
# 1. EXPIRAR solicitudes APROBADAS no despachadas
# ------------------------------------------------

def expirar_aprobadas_vencidas() -> int:
    """
    Pasa a EXPIRADA las solicitudes APROBADAS cuyo fecha_expiracion
    ya pasó. Devuelve la cantidad expirada.

    Idempotente: una vez que una fila pasa a EXPIRADA deja de
    cumplir el filtro estado=APROBADA, así que correr esto de nuevo
    (secuencial o concurrentemente vía select_for_update, que
    vuelve a evaluar el WHERE al desbloquear) no la vuelve a tocar.
    """
    from solicitudes.models import Solicitud

    ahora = timezone.now()

    aprobadas_vencidas = Solicitud.objects.filter(
        estado=Solicitud.EstadoSolicitud.APROBADA,
        fecha_expiracion__lt=ahora,
    )

    if not aprobadas_vencidas.exists():
        return 0

    total = 0
    with transaction.atomic():
        for solicitud in aprobadas_vencidas.select_for_update():
            solicitud.estado = Solicitud.EstadoSolicitud.EXPIRADA
            solicitud.save(update_fields=["estado", "fecha_actualizacion"])

            from .registrar_auditoria import registrar_cambio_estado
            registrar_cambio_estado(
                solicitud       = solicitud,
                estado_anterior = Solicitud.EstadoSolicitud.APROBADA,
                estado_nuevo    = Solicitud.EstadoSolicitud.EXPIRADA,
                usuario         = None,
                nota            = "Expirada automáticamente por el sistema.",
            )
            total += 1

    return total


# ------------------------------------------------
# 2. RECHAZAR solicitudes OBSERVADAS sin respuesta
# ------------------------------------------------

def rechazar_observadas_vencidas() -> int:
    """
    Rechaza las solicitudes OBSERVADAS cuyo plazo de 24h para
    responder venció. Devuelve la cantidad rechazada. Misma
    garantía de idempotencia que expirar_aprobadas_vencidas().
    """
    from solicitudes.models import Solicitud

    ahora = timezone.now()

    observadas_vencidas = Solicitud.objects.filter(
        estado=Solicitud.EstadoSolicitud.OBSERVADA,
        fecha_limite_respuesta__lt=ahora,
    )

    if not observadas_vencidas.exists():
        return 0

    total = 0
    with transaction.atomic():
        for solicitud in observadas_vencidas.select_for_update():
            # El motivo pasa a ser el rechazo automático: es lo que ve el
            # consumidor en su historial y en el email ("Motivo: …"). El
            # texto de la observación original queda en la nota de
            # auditoría del paso a OBSERVADA.
            solicitud.estado          = Solicitud.EstadoSolicitud.RECHAZADA
            solicitud.observacion_anh = MOTIVO_RECHAZO_AUTOMATICO
            solicitud.save(update_fields=["estado", "observacion_anh", "fecha_actualizacion"])

            from .registrar_auditoria import registrar_cambio_estado
            registrar_cambio_estado(
                solicitud       = solicitud,
                estado_anterior = Solicitud.EstadoSolicitud.OBSERVADA,
                estado_nuevo    = Solicitud.EstadoSolicitud.RECHAZADA,
                usuario         = None,
                nota            = (
                    "Rechazada automáticamente por no responder "
                    "la observación dentro del plazo de 24 horas."
                ),
            )
            total += 1

            # Notificar al consumidor recién cuando el rechazo quede
            # confirmado. s=solicitud fija la instancia de esta vuelta.
            transaction.on_commit(lambda s=solicitud: _notificar_rechazo_automatico(s))

    return total


def _notificar_rechazo_automatico(solicitud) -> None:
    """
    Corre después del commit. Un fallo de envío no debe romper el
    resto de las notificaciones del lote ni la request que disparó la
    expiración perezosa: solo se logea.
    """
    try:
        from users.email_service import enviar_notificacion_solicitud_rechazada
        enviar_notificacion_solicitud_rechazada(solicitud)
    except Exception:
        logger.error(
            "No se pudo notificar el rechazo automático de %s",
            solicitud.id_publico, exc_info=True,
        )


# ------------------------------------------------
# PUNTOS DE ENTRADA
# ------------------------------------------------

def expirar_solicitudes_vencidas() -> dict:
    """
    Corre ambas rutinas y logea el resultado si hubo cambios.
    Deja propagar cualquier excepción — la usa el management
    command, donde un fallo debe verse (traceback + exit code
    distinto de cero), no quedar en silencio.
    """
    expiradas  = expirar_aprobadas_vencidas()
    rechazadas = rechazar_observadas_vencidas()

    if expiradas or rechazadas:
        logger.info(
            "Expiración automática: %s solicitud(es) expirada(s), "
            "%s rechazada(s) por vencimiento de plazo.",
            expiradas, rechazadas,
        )

    return {"expiradas": expiradas, "rechazadas": rechazadas}


# Guarda en memoria del proceso: evita repetir el barrido si ya
# corrió hace menos de INTERVALO_MINIMO. Es por-worker (cada proceso
# de Gunicorn tiene su propia copia), no global — alcanza para el
# objetivo real, que es no repetir el chequeo dos o tres veces en el
# mismo segundo cuando una sola carga de página dispara varias
# llamadas (ej. el Dashboard). Las ventanas de expiración de una
# solicitud son de horas, así que una demora de hasta 5 minutos en
# reflejarlo es imperceptible en la práctica.
_ultima_ejecucion_lazy = None
INTERVALO_MINIMO_LAZY = timedelta(minutes=5)


def expirar_solicitudes_vencidas_seguro() -> None:
    """
    Variante para invocar desde el camino de lectura (listados,
    dashboard, estadísticas): nunca debe romper la request que la
    dispara, así que atrapa cualquier excepción y solo la logea.
    Respeta la guarda de INTERVALO_MINIMO_LAZY.
    """
    global _ultima_ejecucion_lazy

    ahora = timezone.now()
    if (
        _ultima_ejecucion_lazy is not None
        and ahora - _ultima_ejecucion_lazy < INTERVALO_MINIMO_LAZY
    ):
        return

    _ultima_ejecucion_lazy = ahora

    try:
        expirar_solicitudes_vencidas()
    except Exception:
        logger.error("Error en expiración automática de solicitudes.", exc_info=True)
