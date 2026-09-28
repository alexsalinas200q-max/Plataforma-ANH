# apps/solicitudes/models.py

import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q


class Solicitud(models.Model):

    # ------------------------------------------------
    # ENUMS
    # ------------------------------------------------

    class EstadoSolicitud(models.TextChoices):
        PENDIENTE  = "PENDIENTE",  "Pendiente"
        OBSERVADA  = "OBSERVADA",  "Observada"
        RECHAZADA  = "RECHAZADA",  "Rechazada"
        CANCELADA  = "CANCELADA",  "Cancelada"
        APROBADA   = "APROBADA",   "Aprobada"
        DESPACHADA = "DESPACHADA", "Despachada"
        EXPIRADA   = "EXPIRADA",   "Expirada"

    class TipoCombustible(models.TextChoices):
        GASOLINA = "GASOLINA", "Gasolina"
        DIESEL   = "DIESEL",   "Diésel"

    # ------------------------------------------------
    # IDENTIFICADOR PÚBLICO
    # ------------------------------------------------

    id_publico = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True
    )

    # ------------------------------------------------
    # RELACIONES PRINCIPALES
    # ------------------------------------------------

    consumidor = models.ForeignKey(
        "consumidores.ConsumidorPerfil",
        on_delete=models.PROTECT,
        related_name="solicitudes"
    )

    estacion_servicio = models.ForeignKey(
        "estaciones.EstacionServicio",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="solicitudes"
    )

    estacion_asignada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_estacion_asignadas"
    )

    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_aprobadas"
    )

    # ------------------------------------------------
    # ESTADO
    # ------------------------------------------------

    estado = models.CharField(
        max_length=20,
        choices=EstadoSolicitud.choices,
        default=EstadoSolicitud.PENDIENTE,
        db_index=True
    )

    # ------------------------------------------------
    # DATOS SOLICITADOS POR EL CONSUMIDOR
    # ------------------------------------------------

    tipo_combustible = models.CharField(
        max_length=20,
        choices=TipoCombustible.choices
    )

    litros_solicitados = models.PositiveIntegerField()

    # ------------------------------------------------
    # DATOS APROBADOS POR ANH
    # ------------------------------------------------

    tipo_combustible_aprobado = models.CharField(
        max_length=20,
        choices=TipoCombustible.choices,
        null=True,
        blank=True
    )

    litros_aprobados = models.PositiveIntegerField(
        null=True,
        blank=True
    )

    observacion_anh = models.TextField(
        blank=True,
        verbose_name="Observación ANH",
        help_text="Motivo de observación o rechazo por parte de la ANH."
    )

    # ------------------------------------------------
    # RESPUESTA DEL CONSUMIDOR A OBSERVACIÓN
    # Nuevos campos para implementar Opción A:
    # Consumidor responde en 24h o la solicitud se rechaza
    # ------------------------------------------------

    respuesta_consumidor = models.TextField(
        blank=True,
        default="",
        verbose_name="Respuesta del consumidor",
        help_text=(
            "Justificación o aclaración del consumidor ante "
            "una observación de la ANH."
        )
    )

    fecha_observacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de observación",
        help_text="Momento en que la ANH marcó la solicitud como OBSERVADA."
    )

    fecha_limite_respuesta = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha límite de respuesta",
        help_text=(
            "El consumidor tiene hasta esta fecha para responder "
            "la observación. Se calcula automáticamente: "
            "fecha_observacion + 24 horas."
        )
    )

    # ------------------------------------------------
    # DATOS DE UBICACIÓN DEL SOLICITANTE
    # ------------------------------------------------

    departamento = models.ForeignKey(
        "catalogos.Departamento",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="solicitudes",
        verbose_name="Departamento"
    )
    provincia = models.ForeignKey(
        "catalogos.Provincia",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="solicitudes",
        verbose_name="Provincia"
    )
    municipio = models.ForeignKey(
        "catalogos.Municipio",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="solicitudes",
        verbose_name="Municipio"
    )
    direccion = models.CharField(
        max_length=100, blank=True, default="",
        verbose_name="Dirección"
    )

    # ------------------------------------------------
    # DATOS DEL FORMULARIO DE SOLICITUD
    # ------------------------------------------------

    actividad = models.CharField(
        max_length=20, blank=True, default="",
        verbose_name="Actividad económica"
    )
    uso_combustible = models.CharField(
        max_length=200, blank=True, default="",
        verbose_name="Uso / destino del combustible"
    )
    documento_justificativo = models.FileField(
        upload_to="solicitudes/documentos_justificativos/",
        null=True, blank=True,
        verbose_name="Documento justificativo",
    )
    documento_respuesta = models.FileField(
    upload_to="solicitudes/documentos_respuesta/",
    null=True, blank=True,
    verbose_name="Documento de respuesta",
    help_text="Documento adjunto por el consumidor al responder una observación."
    )

    # ------------------------------------------------
    # DECLARACIÓN JURADA
    # ------------------------------------------------

    declaracion_jurada_confirmada = models.BooleanField(
        default=False,
        verbose_name="Declaración jurada confirmada"
    )
    fecha_declaracion_jurada = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Fecha de confirmación declaración jurada"
    )

    # ------------------------------------------------
    # DATOS DEL DESPACHO (ESTACIÓN)
    # ------------------------------------------------

    litros_despachados = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    observacion_despacho = models.TextField(
        blank=True,
        default="",
        verbose_name="Observación de despacho",
        help_text=(
            "Nota del operador ESS al registrar el despacho (ej. despacho "
            "parcial, incidencia). Campo propio: antes de 2026-09 se guardaba "
            "por error en observacion_anh, pisando la observación de la ANH."
        ),
    )

    # ------------------------------------------------
    # AUDITORÍA DE USUARIOS
    # ------------------------------------------------

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="solicitudes_creadas"
    )

    despachado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitudes_despachadas"
    )

    # ------------------------------------------------
    # FECHAS
    # ------------------------------------------------

    fecha_creacion      = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    fecha_revision      = models.DateTimeField(null=True, blank=True)
    fecha_aprobacion    = models.DateTimeField(null=True, blank=True)
    fecha_asignacion_estacion = models.DateTimeField(null=True, blank=True)
    fecha_expiracion    = models.DateTimeField(null=True, blank=True)
    fecha_despacho      = models.DateTimeField(null=True, blank=True)

    # ------------------------------------------------
    # CONFIGURACIÓN BD
    # ------------------------------------------------

    class Meta:
        ordering = ["-fecha_creacion"]
        indexes = [
            models.Index(fields=["estado"]),
            models.Index(fields=["estado", "fecha_creacion"]),
            models.Index(fields=["consumidor", "estado"]),
            models.Index(fields=["estacion_servicio", "estado"]),
            # Índice para el cron que busca observadas vencidas
            models.Index(fields=["estado", "fecha_limite_respuesta"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["consumidor"],
                condition=Q(
                    estado__in=[
                        "PENDIENTE",
                        "OBSERVADA",
                        "APROBADA",
                    ]
                ),
                name="unique_solicitud_activa_por_consumidor"
            )
        ]

    # ------------------------------------------------
    # PROPIEDADES
    # ------------------------------------------------

    @property
    def respuesta_plazo_vencido(self) -> bool:
        """
        Retorna True si el plazo de 24h para responder
        la observación ya venció.
        """
        from django.utils import timezone
        if not self.fecha_limite_respuesta:
            return False
        return timezone.now() > self.fecha_limite_respuesta

    @property
    def horas_restantes_respuesta(self) -> int | None:
        """
        Retorna las horas restantes para responder la observación.
        Retorna None si no aplica, 0 si ya venció.
        """
        from django.utils import timezone
        if not self.fecha_limite_respuesta:
            return None
        diff = self.fecha_limite_respuesta - timezone.now()
        return max(0, int(diff.total_seconds() // 3600))

    # ------------------------------------------------
    # VALIDACIONES
    # ------------------------------------------------

    def clean(self):

        if self.litros_solicitados <= 0:
            raise ValidationError(
                "Los litros solicitados deben ser mayores a 0."
            )

        if self.litros_solicitados > 120:
            raise ValidationError(
                "No se pueden solicitar más de 120 litros."
            )

        if self.estado == self.EstadoSolicitud.APROBADA:
            if not self.litros_aprobados:
                raise ValidationError(
                    "Una solicitud aprobada debe tener litros aprobados."
                )
            if not self.tipo_combustible_aprobado:
                raise ValidationError(
                    "Debe definirse el tipo de combustible aprobado."
                )
            if not self.estacion_servicio:
                raise ValidationError(
                    "Debe asignarse una estación de servicio."
                )
            if not self.fecha_expiracion:
                raise ValidationError(
                    "Debe definirse una fecha de expiración."
                )

        if self.estado == self.EstadoSolicitud.DESPACHADA:
            if not self.fecha_despacho:
                raise ValidationError(
                    "Debe registrarse la fecha de despacho."
                )
            if not self.litros_despachados:
                raise ValidationError(
                    "Debe registrarse la cantidad de litros despachados."
                )
            if self.litros_despachados > self.litros_aprobados:
                raise ValidationError(
                    "Los litros despachados no pueden superar los aprobados."
                )

        # Validar que OBSERVADA tenga motivo y fecha límite
        if self.estado == self.EstadoSolicitud.OBSERVADA:
            if not self.observacion_anh:
                raise ValidationError(
                    "Debe ingresar el motivo de la observación."
                )
            if not self.fecha_limite_respuesta:
                raise ValidationError(
                    "Debe definirse la fecha límite de respuesta."
                )

        if self.estado != self.EstadoSolicitud.PENDIENTE:
            if not self.declaracion_jurada_confirmada:
                raise ValidationError(
                    "El solicitante debe confirmar la declaración jurada."
                )

    def __str__(self):
        return f"Solicitud {self.id_publico} - {self.consumidor}"


# ------------------------------------------------
# AUDITORÍA DE ESTADOS
# ------------------------------------------------

class AuditoriaEstadoSolicitud(models.Model):

    solicitud = models.ForeignKey(
        Solicitud,
        on_delete=models.PROTECT,
        related_name="auditoria",
        verbose_name="Solicitud"
    )
    estado_anterior = models.CharField(max_length=20)
    estado_nuevo    = models.CharField(max_length=20)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="auditoria_solicitudes"
    )
    fecha      = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    nota       = models.TextField(blank=True, default="")

    def __str__(self):
        from django.utils import timezone
        return (
            f"Solicitud {str(self.solicitud.id_publico)[:8].upper()} — "
            f"{self.estado_anterior} → {self.estado_nuevo} "
            f"({timezone.localtime(self.fecha).strftime('%d/%m/%Y %H:%M')})"
        )

    class Meta:
        verbose_name        = "Auditoría de Solicitud"
        verbose_name_plural = "Auditoría de Solicitudes"
        ordering            = ["-fecha"]