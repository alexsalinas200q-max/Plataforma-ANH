# apps/solicitudes/services/aprobar_solicitud.py

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from solicitudes.models import Solicitud
from configuracion.models import ConfiguracionSistema


def aprobar_solicitud(
    solicitud_id: int,
    usuario_aprobador,
    estacion_servicio,
    litros_aprobados: int,
    tipo_combustible_aprobado: str,
    observacion_anh: str = "",
) -> Solicitud:

    with transaction.atomic():

        # Bloquea la fila para evitar condiciones de carrera
        solicitud = (
            Solicitud.objects
            .select_for_update()
            .select_related("consumidor")
            .get(id=solicitud_id)
        )

        # -----------------------------------------
        # Validar identidad del consumidor
        # -----------------------------------------

        consumidor = solicitud.consumidor
        if consumidor.estado_identidad != "VERIFICADO":
            raise ValidationError(
                f"No se puede aprobar la solicitud. El consumidor "
                f"'{consumidor.user.nombre_completo()}' no tiene su identidad "
                f"verificada. Estado actual: "
                f"{consumidor.get_estado_identidad_display()}. "
                f"Verifique los documentos antes de aprobar."
            )

        # Validar que el consumidor no esté bloqueado
        if consumidor.esta_bloqueado():
            raise ValidationError(
                f"No se puede aprobar la solicitud. El consumidor "
                f"'{consumidor.user.nombre_completo()}' está bloqueado "
                f"por alerta de repetitividad."
            )

        # -----------------------------------------
        # Validar cupo mensual (120 L/mes, normativa)
        # -----------------------------------------

        from .validar_cupo import verificar_puede_aprobar

        puede, mensaje = verificar_puede_aprobar(solicitud, litros_aprobados)
        if not puede:
            raise ValidationError(mensaje)

        # -----------------------------------------
        # Validar estado actual
        # -----------------------------------------

        if solicitud.estado not in [
            Solicitud.EstadoSolicitud.PENDIENTE,
            Solicitud.EstadoSolicitud.OBSERVADA,
        ]:
            raise ValidationError(
                "Solo se pueden aprobar solicitudes pendientes u observadas."
            )

        # -----------------------------------------
        # Obtener configuración del sistema
        # -----------------------------------------

        config = ConfiguracionSistema.obtener()

        # -----------------------------------------
        # Calcular expiración desde configuración
        # -----------------------------------------

        now = timezone.now()

        fecha_expiracion = now + timezone.timedelta(
            hours=config.tiempo_expiracion_solicitudes_horas
        )

        # -----------------------------------------
        # Detectar modificaciones respecto a lo solicitado (#18)
        # Se registran en la nota de auditoría para trazabilidad.
        # -----------------------------------------

        modificaciones = []

        if tipo_combustible_aprobado != solicitud.tipo_combustible:
            modificaciones.append(
                f"combustible solicitado '{solicitud.tipo_combustible}' "
                f"→ aprobado '{tipo_combustible_aprobado}'"
            )

        if litros_aprobados != solicitud.litros_solicitados:
            modificaciones.append(
                f"litros solicitados {solicitud.litros_solicitados} L "
                f"→ aprobados {litros_aprobados} L"
            )

        # Construir nota de auditoría
        if modificaciones:
            nota_auditoria = (
                f"Aprobado con modificación: {'; '.join(modificaciones)}."
            )
            if observacion_anh:
                nota_auditoria += f" Observación: {observacion_anh}"
        else:
            nota_auditoria = observacion_anh

        # -----------------------------------------
        # Registrar aprobación
        # -----------------------------------------

        solicitud.estado                    = Solicitud.EstadoSolicitud.APROBADA
        solicitud.tipo_combustible_aprobado = tipo_combustible_aprobado
        solicitud.litros_aprobados          = litros_aprobados
        solicitud.estacion_servicio         = estacion_servicio
        solicitud.observacion_anh           = observacion_anh

        # Auditoría — ambos campos apuntan al mismo usuario aprobador
        solicitud.aprobado_por              = usuario_aprobador
        solicitud.estacion_asignada_por     = usuario_aprobador

        # Fechas — un solo now() para consistencia
        solicitud.fecha_aprobacion          = now
        solicitud.fecha_asignacion_estacion = now
        solicitud.fecha_expiracion          = fecha_expiracion

        solicitud.full_clean()
        solicitud.save()

        # Registrar auditoría con nota de modificaciones
        from .registrar_auditoria import registrar_cambio_estado
        registrar_cambio_estado(
            solicitud       = solicitud,
            estado_anterior = Solicitud.EstadoSolicitud.PENDIENTE,
            estado_nuevo    = Solicitud.EstadoSolicitud.APROBADA,
            usuario         = usuario_aprobador,
            nota            = nota_auditoria,
        )

        # Notificar al consumidor
        from users.email_service import enviar_notificacion_solicitud_aprobada
        enviar_notificacion_solicitud_aprobada(solicitud)

        return solicitud