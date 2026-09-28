# apps/consumidores/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone


class ConsumidorPerfil(models.Model):

    class EstadoIdentidad(models.TextChoices):
        PENDIENTE   = "PENDIENTE",   "Pendiente"
        EN_REVISION = "EN_REVISION", "En revisión"
        VERIFICADO  = "VERIFICADO",  "Verificado"
        RECHAZADO   = "RECHAZADO",   "Rechazado"

    class EstadoAlerta(models.TextChoices):
        NORMAL      = "NORMAL",      "Normal"
        EN_REVISION = "EN_REVISION", "En revisión por repetitividad"
        BLOQUEADO   = "BLOQUEADO",   "Bloqueado"

    class ActividadEconomica(models.TextChoices):
        AGRICULTURA  = "AGRICULTURA",  "Agricultura / Ganadería"
        TRANSPORTE   = "TRANSPORTE",   "Transporte"
        INDUSTRIA    = "INDUSTRIA",    "Industria / Manufactura"
        PESCA        = "PESCA",        "Pesca"
        CONSTRUCCION = "CONSTRUCCION", "Construcción"
        DOMESTICO    = "DOMESTICO",    "Uso doméstico"
        COMERCIO     = "COMERCIO",     "Comercio"
        MINERIA      = "MINERIA",      "Minería"
        OTRO         = "OTRO",         "Otro"

    # Relación con User
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consumidor",
        verbose_name="Usuario"
    )

    # Datos personales
    fecha_nacimiento = models.DateField(verbose_name="Fecha de nacimiento")

    celular = models.CharField(
        max_length=20, blank=True, default="", verbose_name="Celular"
    )
    celular_verificado = models.BooleanField(
        default=False, verbose_name="Celular verificado"
    )

    # Ubicación via catálogos
    departamento = models.ForeignKey(
        "catalogos.Departamento",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="consumidores", verbose_name="Departamento"
    )
    provincia = models.ForeignKey(
        "catalogos.Provincia",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="consumidores", verbose_name="Provincia"
    )
    municipio = models.ForeignKey(
        "catalogos.Municipio",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="consumidores", verbose_name="Municipio"
    )
    direccion = models.CharField(
        max_length=100, blank=True, default="", verbose_name="Dirección"
    )

    # Actividad económica
    actividad = models.CharField(
        max_length=20,
        choices=ActividadEconomica.choices,
        blank=True, default="",
        verbose_name="Actividad económica"
    )

    # Estado de identidad
    estado_identidad = models.CharField(
        max_length=20,
        choices=EstadoIdentidad.choices,
        default=EstadoIdentidad.PENDIENTE,
        db_index=True,
        verbose_name="Estado de identidad"
    )

    # Control de repetitividad
    alerta_repetitividad = models.CharField(
        max_length=20,
        choices=EstadoAlerta.choices,
        default=EstadoAlerta.NORMAL,
        db_index=True,
        verbose_name="Alerta de repetitividad"
    )
    fecha_alerta = models.DateTimeField(
        null=True, blank=True, verbose_name="Fecha de alerta"
    )
    motivo_bloqueo = models.TextField(
        blank=True, default="", verbose_name="Motivo de bloqueo"
    )

    # Auditoría
    fecha_creacion      = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def es_mayor_de_edad(self) -> bool:
        hoy = timezone.localdate()
        edad = (
            hoy.year - self.fecha_nacimiento.year
            - (
                (hoy.month, hoy.day)
                < (self.fecha_nacimiento.month, self.fecha_nacimiento.day)
            )
        )
        return edad >= 18

    def esta_bloqueado(self) -> bool:
        return self.alerta_repetitividad == self.EstadoAlerta.BLOQUEADO

    def __str__(self):
        return (
            f"{self.user.nombres} {self.user.apellido_paterno} "
            f"— {self.get_estado_identidad_display()}"
        )

    class Meta:
        verbose_name        = "Perfil Consumidor"
        verbose_name_plural = "Perfiles Consumidor"
        ordering            = ["-fecha_creacion"]


class DocumentoIdentidad(models.Model):

    class TipoDocumento(models.TextChoices):
        CI  = "CI",  "Cédula de Identidad (CI)"
        CIE = "CIE", "Cédula de Identidad de Extranjero (CIE)"

    perfil = models.ForeignKey(
        ConsumidorPerfil,
        on_delete=models.CASCADE,
        related_name="documentos",
        verbose_name="Perfil consumidor"
    )

    tipo_documento = models.CharField(
        max_length=20,
        choices=TipoDocumento.choices,
        verbose_name="Tipo de documento"
    )
    numero_documento = models.CharField(
        max_length=30, unique=True, verbose_name="Número de documento"
    )
    complemento_documento = models.CharField(
        max_length=10, blank=True, default="", verbose_name="Complemento"
    )

    # Fotografías del documento
    anverso = models.ImageField(
        upload_to="documentos/identidad/anverso/",
        verbose_name="Anverso del documento"
    )
    reverso = models.ImageField(
        upload_to="documentos/identidad/reverso/",
        verbose_name="Reverso del documento"
    )
    foto_sosteniendo = models.ImageField(
        upload_to="documentos/identidad/sosteniendo/",
        null=True,
        blank=True,
        verbose_name="Foto sosteniendo el documento",
        help_text=(
            "Fotografía del solicitante sosteniendo su documento "
            "de identidad de frente. Requerida para nuevos registros."
        )
    )

    fecha_subida = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_tipo_documento_display()} — {self.numero_documento}"

    class Meta:
        verbose_name        = "Documento de Identidad"
        verbose_name_plural = "Documentos de Identidad"
        ordering            = ["-fecha_subida"]
        constraints = [
            models.UniqueConstraint(
                fields=["perfil", "tipo_documento"],
                name="unique_tipo_documento_por_perfil"
            )
        ]