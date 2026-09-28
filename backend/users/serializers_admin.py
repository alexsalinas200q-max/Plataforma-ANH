# apps/users/serializers_admin.py
#
# Serializer para cuando un funcionario ANH/ADMIN registra a un consumidor
# (típicamente en atención presencial).
#
# Se separa del RegistroConsumidorSerializer (auto-registro público) porque
# las reglas de negocio son distintas:
#   - Nadie elige contraseña al crear la cuenta: queda inutilizable y el
#     consumidor define la suya desde el link de activación que le llega
#     por email (la view lo envía, ver services.enviar_activacion)
#   - No se envía PIN de verificación: completar el link verifica el email
#   - La cuenta queda PENDIENTE hasta que el consumidor usa el link

from django.db import transaction
from rest_framework import serializers

from .models import User


class RegistroConsumidorPorAdminSerializer(serializers.Serializer):
    """
    Registro de consumidor iniciado por ANH/ADMIN.

    Mismos campos que RegistroConsumidorSerializer EXCEPTO password/password2:
    la contraseña la define el consumidor desde el link de activación.
    """

    # --- Datos de User ---
    email            = serializers.EmailField()
    nombres          = serializers.CharField(max_length=100)
    apellido_paterno = serializers.CharField(max_length=100)
    apellido_materno = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )

    # --- Datos de ConsumidorPerfil ---
    fecha_nacimiento = serializers.DateField()
    celular          = serializers.CharField(max_length=20)

    departamento = serializers.PrimaryKeyRelatedField(queryset=[])
    provincia    = serializers.PrimaryKeyRelatedField(queryset=[])
    municipio    = serializers.PrimaryKeyRelatedField(queryset=[])
    direccion    = serializers.CharField(max_length=100)
    actividad    = serializers.ChoiceField(choices=[])

    # --- Datos de DocumentoIdentidad ---
    tipo_documento        = serializers.ChoiceField(choices=[])
    numero_documento      = serializers.CharField(max_length=30)
    complemento_documento = serializers.CharField(
        max_length=10, required=False, allow_blank=True, default=""
    )
    anverso          = serializers.ImageField()
    reverso          = serializers.ImageField()
    foto_sosteniendo = serializers.ImageField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from catalogos.models import Departamento, Provincia, Municipio
        from consumidores.models import ConsumidorPerfil, DocumentoIdentidad

        self.fields["departamento"].queryset  = Departamento.objects.all()
        self.fields["provincia"].queryset     = Provincia.objects.all()
        self.fields["municipio"].queryset     = Municipio.objects.all()
        self.fields["actividad"].choices      = ConsumidorPerfil.ActividadEconomica.choices
        self.fields["tipo_documento"].choices = DocumentoIdentidad.TipoDocumento.choices

    # ------------------------------------------------
    # VALIDACIONES (mismas que el registro público)
    # ------------------------------------------------

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta registrada con este correo."
            )
        return value

    def validate_numero_documento(self, value):
        from consumidores.models import DocumentoIdentidad
        if DocumentoIdentidad.objects.filter(numero_documento=value).exists():
            raise serializers.ValidationError(
                "Este número de documento ya está registrado en el sistema."
            )
        return value

    def validate_fecha_nacimiento(self, value):
        # Fecha local (La Paz), no la del servidor (UTC en Railway).
        from django.utils import timezone
        hoy  = timezone.localdate()
        edad = (
            hoy.year - value.year
            - ((hoy.month, hoy.day) < (value.month, value.day))
        )
        if edad < 18:
            raise serializers.ValidationError(
                "El consumidor debe ser mayor de 18 años."
            )
        return value

    def validate(self, attrs):
        prov = attrs.get("provincia")
        dep  = attrs.get("departamento")
        if prov and dep and prov.departamento_id != dep.id:
            raise serializers.ValidationError({
                "provincia": "La provincia no pertenece al departamento seleccionado."
            })

        mun = attrs.get("municipio")
        if mun and prov and mun.provincia_id != prov.id:
            raise serializers.ValidationError({
                "municipio": "El municipio no pertenece a la provincia seleccionada."
            })

        return attrs

    def _validar_imagen(self, value, nombre):
        tipos_permitidos = ["image/jpeg", "image/png", "image/webp"]
        limite_mb = 5
        if value.content_type not in tipos_permitidos:
            raise serializers.ValidationError(
                f"El {nombre} debe ser JPG, PNG o WebP."
            )
        if value.size > limite_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"El {nombre} no puede superar los {limite_mb} MB."
            )
        return value

    def validate_anverso(self, value):
        return self._validar_imagen(value, "anverso")

    def validate_reverso(self, value):
        return self._validar_imagen(value, "reverso")

    def validate_foto_sosteniendo(self, value):
        return self._validar_imagen(value, "foto sosteniendo el documento")

    # ------------------------------------------------
    # CREACIÓN
    # Misma orquestación que RegistroConsumidorSerializer.create(),
    # pero sin contraseña: la cuenta queda pendiente de activación.
    # ------------------------------------------------

    @transaction.atomic
    def create(self, validated_data):
        from consumidores.models import ConsumidorPerfil, DocumentoIdentidad

        campos_user   = ["email", "nombres", "apellido_paterno", "apellido_materno"]
        campos_perfil = [
            "fecha_nacimiento", "celular", "departamento",
            "provincia", "municipio", "direccion", "actividad",
        ]
        campos_doc = [
            "tipo_documento", "numero_documento", "complemento_documento",
            "anverso", "reverso", "foto_sosteniendo",
        ]

        user_data   = {k: validated_data.pop(k) for k in campos_user   if k in validated_data}
        perfil_data = {k: validated_data.pop(k) for k in campos_perfil if k in validated_data}
        doc_data    = {k: validated_data.pop(k) for k in campos_doc    if k in validated_data}

        user = User(tipo_usuario=User.TipoUsuario.CONS, **user_data)

        # Contraseña inutilizable + PENDIENTE: es la combinación que
        # identifica una activación pendiente (es_activacion_pendiente).
        # El admin nunca conoce la contraseña del consumidor.
        user.set_unusable_password()
        user.email_verificado         = False
        user.estado_cuenta            = User.EstadoCuenta.PENDIENTE
        user.requiere_cambio_password = False

        user.full_clean()
        user.save()

        perfil = ConsumidorPerfil.objects.create(user=user, **perfil_data)
        DocumentoIdentidad.objects.create(perfil=perfil, **doc_data)

        return user
