# apps/solicitudes/views.py

from rest_framework import mixins, viewsets, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django_filters.rest_framework import DjangoFilterBackend

from .models import Solicitud
from .serializers import (
    SolicitudSerializer,
    SolicitudListSerializer,
    SolicitudCreateSerializer,
    SolicitudAprobarSerializer,
    SolicitudRevisionSerializer,
    SolicitudDespacharSerializer,
)

from .services.aprobar_solicitud import aprobar_solicitud
from .services.despachar_solicitud import despachar_solicitud
from .services.observar_solicitud import observar_solicitud, responder_observacion
from .services.rechazar_solicitud import rechazar_solicitud

from .permissions import (
    EsUsuarioANH,
    EsConsumidor,
    EsEstacionAsignada,
)

from .filters import SolicitudFilter


class SolicitudViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):

    queryset           = Solicitud.objects.none()
    permission_classes = [IsAuthenticated]
    lookup_field       = "id_publico"

    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_class = SolicitudFilter

    ordering_fields = [
        "fecha_creacion", "fecha_aprobacion",
        "fecha_despacho", "litros_solicitados", "litros_aprobados",
    ]
    ordering = ["-fecha_creacion"]

    search_fields = [
        "id_publico",
        "consumidor__user__nombres",
        "consumidor__user__apellido_paterno",
        "consumidor__documentos__numero_documento",
    ]

    # ------------------------------------------------
    # SERIALIZER DINÁMICO
    # ------------------------------------------------

    def get_serializer_class(self):
        if self.action == "list":                         return SolicitudListSerializer
        if self.action == "create":                       return SolicitudCreateSerializer
        if self.action == "aprobar":                      return SolicitudAprobarSerializer
        if self.action in ("observar", "rechazar", "cancelar"): return SolicitudRevisionSerializer
        if self.action == "despachar":                    return SolicitudDespacharSerializer
        return SolicitudSerializer

    # ------------------------------------------------
    # PERMISOS DINÁMICOS
    # ------------------------------------------------

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), EsConsumidor()]
        if self.action in ("aprobar", "observar", "rechazar"):
            return [IsAuthenticated(), EsUsuarioANH()]
        if self.action in ("cancelar", "responder_observacion"):
            return [IsAuthenticated(), EsConsumidor()]
        if self.action == "despachar":
            return [IsAuthenticated(), EsEstacionAsignada()]
        return [IsAuthenticated()]

    # ------------------------------------------------
    # QUERYSET SEGÚN ROL
    # ------------------------------------------------

    def get_queryset(self):
        # Solo en list: corrige solicitudes APROBADA/OBSERVADA vencidas
        # antes de mostrarlas, sin depender de un proceso programado
        # (ver solicitudes/services/expirar_solicitudes.py). No se
        # engancha en retrieve ni en las acciones de escritura
        # (aprobar/despachar/observar/rechazar/cancelar), que ya tienen
        # su propia transacción y no necesitan esta query de más.
        if self.action == "list":
            from .services.expirar_solicitudes import expirar_solicitudes_vencidas_seguro
            expirar_solicitudes_vencidas_seguro()

        user = self.request.user
        base_qs = Solicitud.objects.select_related(
            # Consumidor + su usuario (evita N+1 al llamar consumidor.user.nombre)
            "consumidor__user",
            # Estación + municipio
            "estacion_servicio__municipio__provincia__departamento",
            # Usuarios relacionados
            "creado_por",
            "aprobado_por",
            "despachado_por",
            # Ubicación geográfica de la solicitud
            "departamento",
            "provincia",
            "municipio",
        ).prefetch_related(
            # Auditoría: se muestra en el detalle
            "auditoria__usuario",
            # Documentos del consumidor: el listado ESS muestra el CI
            "consumidor__documentos",
        )
        if user.tipo_usuario in ["ANH", "ADMIN"]:
            return base_qs
        if hasattr(user, "consumidor"):
            return base_qs.filter(consumidor=user.consumidor)
        if hasattr(user, "perfil_funcionario") and user.perfil_funcionario.estacion_servicio:
            return base_qs.filter(
                estacion_servicio=user.perfil_funcionario.estacion_servicio
            )
        return base_qs.none()

    # ------------------------------------------------
    # HELPERS
    # ------------------------------------------------

    def _get_solicitud(self, id_publico):
        return get_object_or_404(self.get_queryset(), id_publico=id_publico)

    def _manejar_error_negocio(self, exc):
        if isinstance(exc, DjangoValidationError):
            raise ValidationError(detail=exc.messages)
        raise exc

    # ------------------------------------------------
    # CREAR SOLICITUD (CONSUMIDOR)
    # ------------------------------------------------

    def create(self, request, *args, **kwargs):
        if not hasattr(request.user, "consumidor"):
            raise PermissionDenied("Solo los consumidores pueden crear solicitudes.")

        consumidor = request.user.consumidor

        if consumidor.esta_bloqueado():
            raise PermissionDenied(
                "Tu cuenta está bloqueada por repetitividad. "
                "Contacta a la ANH para más información."
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from django.utils import timezone

        try:
            solicitud = Solicitud.objects.create(
                consumidor             = consumidor,
                creado_por             = request.user,
                tipo_combustible       = serializer.validated_data["tipo_combustible"],
                litros_solicitados     = serializer.validated_data["litros_solicitados"],
                uso_combustible        = serializer.validated_data.get("uso_combustible", ""),
                documento_justificativo = serializer.validated_data.get("documento_justificativo"),
                declaracion_jurada_confirmada = serializer.validated_data.get(
                    "declaracion_jurada_confirmada", False
                ),
                fecha_declaracion_jurada = timezone.now(),
                # Ubicación y estación: las elige el consumidor en el
                # formulario (puede diferir de su perfil registrado).
                departamento = serializer.validated_data["departamento"],
                provincia    = serializer.validated_data["provincia"],
                municipio    = serializer.validated_data["municipio"],
                estacion_servicio = serializer.validated_data["estacion_servicio"],
                # Dirección y actividad económica siguen viniendo del
                # perfil del consumidor (no se piden de nuevo en cada
                # solicitud).
                direccion    = consumidor.direccion,
                actividad    = consumidor.actividad,
            )
        except DjangoValidationError as e:
            self._manejar_error_negocio(e)
        except IntegrityError:
            # Red de seguridad contra condiciones de carrera: el chequeo de
            # verificar_puede_crear_solicitud ya cubre este caso en el
            # camino normal, pero la constraint de BD (unique_solicitud_
            # activa_por_consumidor) sigue siendo la garantía dura si dos
            # requests llegan casi simultáneas.
            raise ValidationError(
                "Ya tienes una solicitud activa. No puedes crear otra "
                "hasta que se cierre."
            )

        return Response(
            SolicitudSerializer(solicitud).data,
            status=status.HTTP_201_CREATED
        )

    # ------------------------------------------------
    # APROBAR SOLICITUD (ANH)
    # ------------------------------------------------

    @action(detail=True, methods=["post"])
    def aprobar(self, request, id_publico=None):
        solicitud = self._get_solicitud(id_publico)
        self.check_object_permissions(request, solicitud)

        serializer = self.get_serializer(
            data=request.data,
            context={"solicitud": solicitud}
        )
        serializer.is_valid(raise_exception=True)

        try:
            solicitud = aprobar_solicitud(
                solicitud_id              = solicitud.id,
                usuario_aprobador         = request.user,
                estacion_servicio         = serializer.validated_data["estacion_servicio"],
                litros_aprobados          = serializer.validated_data["litros_aprobados"],
                tipo_combustible_aprobado = serializer.validated_data["tipo_combustible_aprobado"],
                observacion_anh           = serializer.validated_data.get("observacion_anh", ""),
            )
        except DjangoValidationError as e:
            self._manejar_error_negocio(e)

        return Response(SolicitudSerializer(solicitud).data, status=status.HTTP_200_OK)

    # ------------------------------------------------
    # OBSERVAR SOLICITUD (ANH)
    # ------------------------------------------------

    @action(detail=True, methods=["post"])
    def observar(self, request, id_publico=None):
        solicitud = self._get_solicitud(id_publico)
        self.check_object_permissions(request, solicitud)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            solicitud = observar_solicitud(
                solicitud       = solicitud,
                usuario         = request.user,
                observacion_anh = serializer.validated_data["observacion_anh"],
            )
        except DjangoValidationError as e:
            self._manejar_error_negocio(e)

        return Response(SolicitudSerializer(solicitud).data, status=status.HTTP_200_OK)

    # ------------------------------------------------
    # RESPONDER OBSERVACIÓN (CONSUMIDOR)
    # ------------------------------------------------

    @action(detail=True, methods=["post"], url_path="responder-observacion")
    def responder_observacion(self, request, id_publico=None):
        """
        El consumidor responde la observación de la ANH.
        La solicitud vuelve a PENDIENTE si el plazo no ha vencido.
        Acepta un documento adjunto opcional (multipart/form-data).
        """
        solicitud = self._get_solicitud(id_publico)

        if not hasattr(request.user, "consumidor"):
            raise PermissionDenied("Solo los consumidores pueden responder observaciones.")

        if solicitud.consumidor != request.user.consumidor:
            raise PermissionDenied("No tienes permiso para responder esta solicitud.")

        respuesta = request.data.get("respuesta", "").strip()
        documento = request.FILES.get("documento_respuesta", None)

        try:
            solicitud = responder_observacion(
                solicitud  = solicitud,
                usuario    = request.user,
                respuesta  = respuesta,
                documento  = documento,
            )
        except DjangoValidationError as e:
            self._manejar_error_negocio(e)

        return Response(SolicitudSerializer(solicitud).data, status=status.HTTP_200_OK)

    # ------------------------------------------------
    # RECHAZAR SOLICITUD (ANH)
    # ------------------------------------------------

    @action(detail=True, methods=["post"])
    def rechazar(self, request, id_publico=None):
        solicitud = self._get_solicitud(id_publico)
        self.check_object_permissions(request, solicitud)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            solicitud = rechazar_solicitud(
                solicitud       = solicitud,
                usuario         = request.user,
                observacion_anh = serializer.validated_data["observacion_anh"],
            )
        except DjangoValidationError as e:
            self._manejar_error_negocio(e)

        return Response(SolicitudSerializer(solicitud).data, status=status.HTTP_200_OK)

    # ------------------------------------------------
    # DESPACHAR SOLICITUD (ESTACIÓN)
    # ------------------------------------------------

    @action(detail=True, methods=["post"])
    def despachar(self, request, id_publico=None):
        solicitud = self._get_solicitud(id_publico)
        self.check_object_permissions(request, solicitud)

        serializer = self.get_serializer(
            data=request.data,
            context={"solicitud": solicitud}
        )
        serializer.is_valid(raise_exception=True)

        try:
            solicitud = despachar_solicitud(
                solicitud          = solicitud,
                usuario            = request.user,
                litros_despachados = serializer.validated_data["litros_despachados"],
                observacion        = serializer.validated_data.get("observacion", ""),
            )
        except DjangoValidationError as e:
            self._manejar_error_negocio(e)

        return Response(SolicitudSerializer(solicitud).data, status=status.HTTP_200_OK)

    # ------------------------------------------------
    # CANCELAR SOLICITUD (CONSUMIDOR)
    # ------------------------------------------------

    @action(detail=True, methods=["post"])
    def cancelar(self, request, id_publico=None):
        solicitud = self._get_solicitud(id_publico)
        self.check_object_permissions(request, solicitud)

        if solicitud.consumidor != request.user.consumidor:
            raise PermissionDenied("No puedes cancelar una solicitud que no te pertenece.")

        if solicitud.estado not in [
            Solicitud.EstadoSolicitud.PENDIENTE,
            Solicitud.EstadoSolicitud.OBSERVADA,
        ]:
            raise ValidationError("Solo puedes cancelar solicitudes pendientes u observadas.")

        estado_anterior = solicitud.estado

        solicitud.estado = Solicitud.EstadoSolicitud.CANCELADA
        solicitud.save(update_fields=["estado", "fecha_actualizacion"])

        from .services.registrar_auditoria import registrar_cambio_estado
        registrar_cambio_estado(
            solicitud       = solicitud,
            estado_anterior = estado_anterior,
            estado_nuevo    = Solicitud.EstadoSolicitud.CANCELADA,
            usuario         = request.user,
            nota            = "Cancelada por el consumidor.",
        )

        return Response(SolicitudSerializer(solicitud).data, status=status.HTTP_200_OK)

    # ------------------------------------------------
    # DECLARACIÓN JURADA PDF
    # ------------------------------------------------

    @action(detail=True, methods=["get"], url_path="declaracion-jurada")
    def declaracion_jurada(self, request, id_publico=None):
        solicitud = self._get_solicitud(id_publico)

        from .services.generar_declaracion_jurada import generar_declaracion_jurada
        from django.http import HttpResponse

        pdf_bytes = generar_declaracion_jurada(solicitud)
        nombre    = f"declaracion_jurada_{str(solicitud.id_publico)[:8].upper()}.pdf"

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return response

    # ------------------------------------------------
    # COMPROBANTE PDF
    # ------------------------------------------------

    @action(detail=True, methods=["get"], url_path="comprobante")
    def comprobante(self, request, id_publico=None):
        solicitud = self._get_solicitud(id_publico)

        if solicitud.estado != Solicitud.EstadoSolicitud.APROBADA:
            raise ValidationError(
                "El comprobante solo está disponible para solicitudes aprobadas."
            )

        from .services.generar_comprobante import generar_comprobante
        from django.http import HttpResponse

        pdf_bytes = generar_comprobante(solicitud)
        nombre    = f"comprobante_{str(solicitud.id_publico)[:8].upper()}.pdf"

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{nombre}"'
        return response


# ------------------------------------------------
# CUPO MENSUAL — CONSUMIDOR AUTENTICADO
# ------------------------------------------------

class MiDisponibleView(APIView):
    """
    GET /api/solicitudes/mi-disponible/

    Cupo mensual y solicitud activa del consumidor autenticado.
    Usado por el widget de cupo y el formulario de nueva solicitud
    en el frontend para no dejar que el consumidor intente algo que
    el backend va a rechazar de todas formas.
    """

    permission_classes = [EsConsumidor]

    def get(self, request):
        from .services.validar_cupo import calcular_cupo_mensual, obtener_solicitud_activa

        consumidor = request.user.consumidor
        cupo       = calcular_cupo_mensual(consumidor)
        activa     = obtener_solicitud_activa(consumidor)

        return Response({
            "total_mes":   cupo["total"],
            "usado":       cupo["usado"],
            "disponible":  cupo["disponible"],
            "mes":         cupo["mes"],
            "tiene_activa": activa is not None,
            "solicitud_activa": (
                {
                    "id_publico":         activa.id_publico,
                    "estado":             activa.estado,
                    "litros_solicitados": activa.litros_solicitados,
                }
                if activa is not None else None
            ),
        })


# ------------------------------------------------
# CUPO MENSUAL — CONSULTA POR ANH/ADMIN
# ------------------------------------------------

class CupoConsumidorView(APIView):
    """
    GET /api/solicitudes/cupo-consumidor/<consumidor_id>/

    Cupo mensual de un consumidor puntual, para que ANH lo vea antes
    de aprobar (el modal de aprobación lo consulta al abrirse). Sin
    tiene_activa/solicitud_activa: ANH ya está viendo la solicitud
    puntual que va a aprobar, no necesita ese dato acá.
    """

    permission_classes = [EsUsuarioANH]

    def get(self, request, consumidor_id):
        from consumidores.models import ConsumidorPerfil
        from .services.validar_cupo import calcular_cupo_mensual

        try:
            consumidor = ConsumidorPerfil.objects.get(id=consumidor_id)
        except ConsumidorPerfil.DoesNotExist:
            raise NotFound("Consumidor no encontrado.")

        cupo = calcular_cupo_mensual(consumidor)

        return Response({
            "total_mes":  cupo["total"],
            "usado":      cupo["usado"],
            "disponible": cupo["disponible"],
            "mes":        cupo["mes"],
        })