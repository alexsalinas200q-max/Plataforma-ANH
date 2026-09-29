# apps/estaciones/serializers.py

from rest_framework import serializers

from .models import EstacionServicio


# ------------------------------------------------
# OPERADORES ESS (LECTURA)
# Muestra los funcionarios ESS asignados
# a la estación via PerfilFuncionario.
# ------------------------------------------------

class OperadorEstacionSerializer(serializers.Serializer):
    """
    Lectura liviana de los operadores ESS
    asignados a una estación.
    """

    id             = serializers.IntegerField(source="user.id")
    nombre_completo = serializers.SerializerMethodField()
    email          = serializers.EmailField(source="user.email")
    cargo          = serializers.CharField()
    celular        = serializers.CharField()

    def get_nombre_completo(self, obj):
        return obj.user.nombre_completo()


# ------------------------------------------------
# LECTURA DE ESTACIÓN
# ------------------------------------------------

class EstacionServicioReadSerializer(serializers.ModelSerializer):
    """
    Serializer de lectura completa de una estación.
    Incluye operadores ESS asignados y datos de auditoría.
    """

    creada_por_nombre   = serializers.SerializerMethodField()
    operadores          = OperadorEstacionSerializer(many=True, read_only=True)
    total_solicitudes   = serializers.SerializerMethodField()
    provincia_id    = serializers.IntegerField(
        source="municipio.provincia.id", read_only=True
    )
    departamento_id = serializers.IntegerField(
        source="municipio.provincia.departamento.id", read_only=True
    )
    municipio_nombre    = serializers.CharField(
        source="municipio.nombre", read_only=True
    )
    departamento_nombre = serializers.CharField(
        source="municipio.provincia.departamento.nombre", read_only=True
    )

    class Meta:
        model = EstacionServicio
        fields = [
            "id",
            "nombre",
            "codigo",
            "direccion",
            "provincia_id", 
            "departamento_id",
            "municipio",
            "municipio_nombre",
            "departamento_nombre",
            "estado",
            "operadores",
            "total_solicitudes",
            "creada_por",
            "creada_por_nombre",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields

    def get_creada_por_nombre(self, obj):
        if obj.creada_por:
            return obj.creada_por.nombre_completo()
        return None

    def get_total_solicitudes(self, obj):
        """
        Total de solicitudes asignadas a esta estación.
        Solo cuenta APROBADAS y DESPACHADAS.
        """
        return obj.solicitudes.filter(
            estado__in=["APROBADA", "DESPACHADA"]
        ).count()


# ------------------------------------------------
# LISTADO DE ESTACIONES (OPTIMIZADO)
# ------------------------------------------------

class EstacionServicioListSerializer(serializers.ModelSerializer):
    """
    Serializer liviano para listados: sin el detalle de operadores
    (nombre, email, celular), solo el conteo.
    """

    municipio_nombre    = serializers.CharField(
        source="municipio.nombre", read_only=True
    )
    departamento_nombre = serializers.CharField(
        source="municipio.provincia.departamento.nombre", read_only=True
    )
    provincia_id    = serializers.IntegerField(
        source="municipio.provincia.id", read_only=True
    )
    departamento_id = serializers.IntegerField(
        source="municipio.provincia.departamento.id", read_only=True
    )
    operadores_count = serializers.SerializerMethodField()

    class Meta:
        model = EstacionServicio
        fields = [
            "id",
            "nombre",
            "codigo",
            # La tarjeta del listado la muestra y el modal de edición
            # arranca con el objeto del listado: sin este campo, el
            # formulario abría con Dirección vacía (obligatoria).
            "direccion",
            "provincia_id",
            "departamento_id",
            "municipio",
            "municipio_nombre",
            "departamento_nombre",
            "estado",
            "operadores_count",
        ]

    def get_operadores_count(self, obj):
        # len() en vez de .count(): el queryset base de la vista ya
        # hace prefetch_related("funcionarios__user") para toda acción
        # (list incluida), así que obj.funcionarios.all() ya está en
        # caché — .count() ignoraría esa caché y dispararía una query
        # nueva por cada estación de la lista.
        return len(obj.funcionarios.all())


# ------------------------------------------------
# ESCRITURA DE ESTACIÓN (CREAR / EDITAR)
# ------------------------------------------------

class EstacionServicioWriteSerializer(serializers.ModelSerializer):
    """
    Serializer de escritura para crear y editar estaciones.
    La asignación de operadores ESS se hace desde
    PerfilFuncionario, no desde aquí.
    """

    class Meta:
        model = EstacionServicio
        fields = [
            "nombre",
            "codigo",
            "direccion",
            "municipio",
            "estado",
        ]

    def validate_codigo(self, value):
        """
        Valida que el código sea único.
        Excluye la instancia actual en caso de edición.
        """
        qs = EstacionServicio.objects.filter(codigo=value)

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe una estación con este código."
            )

        return value.upper()


# ------------------------------------------------
# CAMBIAR ESTADO DE ESTACIÓN
# ------------------------------------------------

class EstacionCambiarEstadoSerializer(serializers.Serializer):
    """
    Permite cambiar el estado de una estación
    entre ACTIVA, INACTIVA y SUSPENDIDA.
    """

    estado = serializers.ChoiceField(
        choices=EstacionServicio.EstadoEstacion.choices
    )

    motivo = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Motivo del cambio de estado (opcional)."
    )