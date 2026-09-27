# apps/solicitudes/services/despachar_solicitud.py

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from solicitudes.models import Solicitud


def despachar_solicitud(
    solicitud: Solicitud,
    usuario,
    litros_despachados: int,
    observacion: str = "",
) -> Solicitud:

    with transaction.atomic():

        # Bloquea la fila para evitar condiciones de carrera
        solicitud = (
        Solicitud.objects
        .select_for_update()
        .get(id=solicitud.id)
        )

        # -----------------------------------------
        # Validar estado actual
        # -----------------------------------------

        if solicitud.estado != Solicitud.EstadoSolicitud.APROBADA:
            raise ValidationError(
                "Solo se pueden despachar solicitudes aprobadas."
            )

        # -----------------------------------------
        # Validar que no haya expirado
        # -----------------------------------------

        if solicitud.fecha_expiracion and timezone.now() > solicitud.fecha_expiracion:
            raise ValidationError(
                "La solicitud ha expirado y no puede ser despachada."
            )

        # -----------------------------------------
        # Validar litros despachados
        # -----------------------------------------

        if litros_despachados <= 0:
            raise ValidationError(
                "Los litros despachados deben ser mayores a 0."
            )

        if litros_despachados > solicitud.litros_aprobados:
            raise ValidationError(
                f"No se pueden despachar más litros de los aprobados "
                f"({solicitud.litros_aprobados} L)."
            )

        # -----------------------------------------
        # Registrar despacho
        # -----------------------------------------

        now = timezone.now()

        estado_anterior = solicitud.estado

        solicitud.estado                = Solicitud.EstadoSolicitud.DESPACHADA
        solicitud.litros_despachados    = litros_despachados  # Real entregado
        solicitud.observacion_despacho  = observacion
        solicitud.despachado_por        = usuario
        solicitud.fecha_despacho        = now

        # litros_aprobados se preserva intacto para trazabilidad
        # observacion_anh NO se toca acá: es de la ANH (aprobar/observar/
        # rechazar), observacion_despacho es la nota propia del despacho.
        # Antes de 2026-09 esta línea pisaba observacion_anh por error.

        solicitud.full_clean()
        solicitud.save()

        # El despacho es la última transición del ciclo de vida y hasta
        # 2026-09 no quedaba en la auditoría, a diferencia de
        # aprobar/observar/rechazar/cancelar.
        from .registrar_auditoria import registrar_cambio_estado
        registrar_cambio_estado(
            solicitud       = solicitud,
            estado_anterior = estado_anterior,
            estado_nuevo    = Solicitud.EstadoSolicitud.DESPACHADA,
            usuario         = usuario,
            nota            = f"Despacho: {observacion}" if observacion else "",
        )

        # verificar_repetitividad ya no se llama acá — ver DEPRECATED en
        # services/verificar_repetitividad.py. El cupo mensual (la regla
        # que exige la normativa) ahora se hace cumplir de forma bloqueante
        # aguas arriba, en creación y aprobación (validar_cupo.py) — antes
        # ninguna de las 4 reglas de verificar_repetitividad bloqueaba nada,
        # solo generaban una alerta después del hecho.

        return solicitud