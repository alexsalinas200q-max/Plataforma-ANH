# apps/solicitudes/serializers.py

from rest_framework import serializers
from .models import Solicitud, AuditoriaEstadoSolicitud


# ------------------------------------------------
# AUDITORIA SERIALIZER
# ------------------------------------------------

class AuditoriaEstadoSerializer(serializers.ModelSerializer):

    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model  = AuditoriaEstadoSolicitud
        fields = [
            "id",
            "estado_anterior",
            "estado_nuevo",
            "usuario_nombre",
            "fecha",
            "ip_address",
            "nota",
        ]
        read_only_fields = fields

    def get_usuario_nombre(self, obj):
        if obj.usuario:
            return obj.usuario.nombre_completo()
        return "Sistema"


# ------------------------------------------------
# SERIALIZER BASE (LECTURA DETALLADA)
# ------------------------------------------------

class SolicitudSerializer(serializers.ModelSerializer):

    consumidor          = serializers.SerializerMethodField()
    auditoria           = AuditoriaEstadoSerializer(many=True, read_only=True)
    departamento_nombre = serializers.CharField(
        source="departamento.nombre", default="—", read_only=True
    )
    provincia_nombre = serializers.CharField(
        source="provincia.nombre", default="—", read_only=True
    )
    municipio_nombre = serializers.CharField(
        source="municipio.nombre", default="—", read_only=True
    )
    estacion_nombre = serializers.CharField(
        source="estacion_servicio.nombre", default="—", read_only=True
    )

    class Meta:
        model = Solicitud
        fields = [
            "id_publico",
            "consumidor",
            "estado",
            "tipo_combustible",
            "litros_solicitados",
            "uso_combustible",
            "actividad",
            "departamento",
            "departamento_nombre",
            "provincia",
            "provincia_nombre",
            "municipio",
            "municipio_nombre",
            "direccion",
            "documento_justificativo",
            "documento_respuesta",
            "declaracion_jurada_confirmada",
            "fecha_declaracion_jurada",
            "tipo_combustible_aprobado",
            "litros_aprobados",
            "litros_despachados",
            "observacion_anh",
            "observacion_despacho",
            "estacion_servicio",
            "estacion_nombre",
            "fecha_creacion",
            "fecha_aprobacion",
            "fecha_expiracion",
            "fecha_despacho",
            "auditoria",
            # Campos para respuesta de observación
            "respuesta_consumidor",
            "fecha_observacion",
            "fecha_limite_respuesta",
            "horas_restantes_respuesta",
            "respuesta_plazo_vencido",
        ]
        read_only_fields = fields

    horas_restantes_respuesta = serializers.IntegerField(read_only=True)
    respuesta_plazo_vencido   = serializers.BooleanField(read_only=True)

    def get_consumidor(self, obj):
        try:
            perfil = obj.consumidor
            return {
                "id":              perfil.id,
                "nombre_completo": perfil.user.nombre_completo(),
                "email":           perfil.user.email,
            }
        except Exception:
            return None


# ------------------------------------------------
# LISTADO (OPTIMIZADO)
# ------------------------------------------------

class SolicitudListSerializer(serializers.ModelSerializer):

    consumidor_nombre    = serializers.SerializerMethodField()
    consumidor_email     = serializers.SerializerMethodField()
    consumidor_documento = serializers.SerializerMethodField()

    class Meta:
        model = Solicitud
        fields = [
            "id_publico",
            "consumidor_nombre",
            "consumidor_email",
            "consumidor_documento",
            "estado",
            "tipo_combustible",
            "tipo_combustible_aprobado",
            "litros_solicitados",
            "litros_aprobados",
            "litros_despachados",
            # Motivo de observación/rechazo: el historial del consumidor
            # (MiSolicitud) se arma con este listado, no con el detalle.
            "observacion_anh",
            "observacion_despacho",
            "uso_combustible",
            "fecha_aprobacion",
            "fecha_expiracion",
            "fecha_despacho",
            "fecha_creacion",
        ]

    def get_consumidor_nombre(self, obj):
        try:
            return obj.consumidor.user.nombre_completo()
        except Exception:
            return "—"

    def get_consumidor_email(self, obj):
        try:
            return obj.consumidor.user.email
        except Exception:
            return "—"

    def get_consumidor_documento(self, obj):
        """
        Documento de identidad del consumidor.
        Lo necesita el operador ESS para cotejar el CI físico
        contra el sistema antes de entregar el combustible.
        """
        try:
            # .all() en lugar de .first() para aprovechar el
            # prefetch_related y no disparar una query por fila.
            docs = obj.consumidor.documentos.all()
            if not docs:
                return None
            doc = docs[0]
            partes = [
                doc.tipo_documento,
                doc.numero_documento,
                doc.complemento_documento,
            ]
            return " ".join(p for p in partes if p).strip()
        except Exception:
            return None


# ------------------------------------------------
# CREAR SOLICITUD (CONSUMIDOR)
# ------------------------------------------------

class SolicitudCreateSerializer(serializers.ModelSerializer):
    """
    Al crear una solicitud, el consumidor indica su ubicación
    actual (Departamento/Provincia/Municipio) y su Estación de
    Servicio de preferencia (obligatoria, debe pertenecer al
    municipio indicado).

    No se asume la ubicación del ConsumidorPerfil (registrada
    en su momento), ya que el consumidor puede haberse mudado
    desde entonces.
    """

    departamento = serializers.PrimaryKeyRelatedField(queryset=[])
    provincia    = serializers.PrimaryKeyRelatedField(queryset=[])
    municipio    = serializers.PrimaryKeyRelatedField(queryset=[])
    estacion_servicio = serializers.PrimaryKeyRelatedField(queryset=[])

    class Meta:
        model = Solicitud
        fields = [
            "tipo_combustible",
            "litros_solicitados",
            "uso_combustible",
            "documento_justificativo",
            "documento_respuesta",
            "declaracion_jurada_confirmada",
            "departamento",
            "provincia",
            "municipio",
            "estacion_servicio",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from catalogos.models import Departamento, Provincia, Municipio
        from estaciones.models import EstacionServicio
        self.fields["departamento"].queryset = Departamento.objects.all()
        self.fields["provincia"].queryset    = Provincia.objects.all()
        self.fields["municipio"].queryset    = Municipio.objects.all()
        self.fields["estacion_servicio"].queryset = (
            EstacionServicio.objects.filter(estado="ACTIVA")
        )

    def validate(self, attrs):
        from .services.validar_cupo import verificar_puede_crear_solicitud

        consumidor = self.context["request"].user.consumidor
        litros     = attrs.get("litros_solicitados")

        puede, mensaje = verificar_puede_crear_solicitud(consumidor, litros)
        if not puede:
            raise serializers.ValidationError(mensaje)

        dep  = attrs.get("departamento")
        prov = attrs.get("provincia")
        mun  = attrs.get("municipio")
        est  = attrs.get("estacion_servicio")

        if prov and dep and prov.departamento_id != dep.id:
            raise serializers.ValidationError({
                "provincia": "La provincia no pertenece al departamento seleccionado."
            })

        if mun and prov and mun.provincia_id != prov.id:
            raise serializers.ValidationError({
                "municipio": "El municipio no pertenece a la provincia seleccionada."
            })

        if est and mun and est.municipio_id != mun.id:
            raise serializers.ValidationError({
                "estacion_servicio": (
                    "La estación seleccionada no pertenece al municipio indicado."
                )
            })

        return attrs

    def validate_litros_solicitados(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Los litros solicitados deben ser mayores a 0."
            )
        if value > 120:
            raise serializers.ValidationError(
                "El máximo permitido es 120 litros."
            )
        return value

    def validate_declaracion_jurada_confirmada(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "Debe confirmar la declaración jurada para continuar."
            )
        return value

    def validate_documento_justificativo(self, value):
        if value:
            tipos_permitidos = [
                "image/jpeg", "image/png",
                "image/webp", "application/pdf"
            ]
            limite_mb = 10
            if value.content_type not in tipos_permitidos:
                raise serializers.ValidationError(
                    "El documento debe ser PDF, JPG, PNG o WebP."
                )
            if value.size > limite_mb * 1024 * 1024:
                raise serializers.ValidationError(
                    f"El documento no puede superar los {limite_mb} MB."
                )
        return value


# ------------------------------------------------
# OBSERVAR / RECHAZAR SOLICITUD (ANH)
# ------------------------------------------------

class SolicitudRevisionSerializer(serializers.Serializer):

    observacion_anh = serializers.CharField(
        min_length=10,
        error_messages={
            "blank":      "Debe ingresar una observación.",
            "min_length": "La observación debe tener al menos 10 caracteres.",
        }
    )


# ------------------------------------------------
# APROBAR SOLICITUD (ANH)
# ------------------------------------------------

class SolicitudAprobarSerializer(serializers.Serializer):

    tipo_combustible_aprobado = serializers.ChoiceField(
        choices=Solicitud.TipoCombustible.choices
    )
    litros_aprobados  = serializers.IntegerField()
    observacion_anh   = serializers.CharField(
        required=False, allow_blank=True
    )
    estacion_servicio = serializers.PrimaryKeyRelatedField(
        queryset=[],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from estaciones.models import EstacionServicio
        self.fields["estacion_servicio"].queryset = (
            EstacionServicio.objects.filter(estado="ACTIVA")
        )

    def validate_litros_aprobados(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Los litros aprobados deben ser mayores a 0."
            )
        if value > 120:
            raise serializers.ValidationError(
                "No se pueden aprobar más de 120 litros."
            )
        return value

    def validate(self, attrs):
        solicitud = self.context.get("solicitud")
        if solicitud and attrs["litros_aprobados"] > solicitud.litros_solicitados:
            raise serializers.ValidationError({
                "litros_aprobados": (
                    "No se pueden aprobar más litros de los solicitados "
                    f"({solicitud.litros_solicitados} L)."
                )
            })
        return attrs


# ------------------------------------------------
# DESPACHAR SOLICITUD (ESTACION)
# ------------------------------------------------

class SolicitudDespacharSerializer(serializers.Serializer):

    confirmar          = serializers.BooleanField()
    litros_despachados = serializers.IntegerField()
    observacion        = serializers.CharField(
        required=False, allow_blank=True, default=""
    )

    def validate_confirmar(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "Debe confirmar el despacho explícitamente."
            )
        return value

    def validate_litros_despachados(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Los litros despachados deben ser mayores a 0."
            )
        return value

    def validate(self, attrs):
        solicitud = self.context.get("solicitud")
        if solicitud:
            litros_aprobados = solicitud.litros_aprobados or 0
            if attrs["litros_despachados"] > litros_aprobados:
                raise serializers.ValidationError({
                    "litros_despachados": (
                        "No se pueden despachar más litros de los aprobados "
                        f"({litros_aprobados} L)."
                    )
                })
        return attrs