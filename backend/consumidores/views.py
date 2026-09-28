# apps/consumidores/views.py

import logging

from rest_framework import mixins, viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.views import APIView

from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend

from users.permissions import IsAdminOrANH, IsConsumidor
from users.services import (
    MENSAJE_RESET_CUENTA_PENDIENTE,
    es_activacion_pendiente,
    resetear_password_por_link,
)

logger = logging.getLogger(__name__)

from .models import ConsumidorPerfil, DocumentoIdentidad
from .serializers import (
    ConsumidorPerfilSerializer,
    ConsumidorPerfilListSerializer,
    ConsumidorPerfilUpdateSerializer,
    DocumentoIdentidadSerializer,
    DocumentoIdentidadWriteSerializer,
    CambiarEstadoIdentidadSerializer,
    CambiarAlertaSerializer,
)


# ------------------------------------------------
# PERFIL PROPIO DEL CONSUMIDOR AUTENTICADO
# ------------------------------------------------

class MiPerfilConsumidorView(APIView):
    """
    GET  /consumidores/me/  → ver perfil completo
    PATCH /consumidores/me/ → actualizar datos editables
    """

    permission_classes = [IsAuthenticated, IsConsumidor]

    def get(self, request):
        serializer = ConsumidorPerfilSerializer(request.user.consumidor)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = ConsumidorPerfilUpdateSerializer(
            request.user.consumidor,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            ConsumidorPerfilSerializer(request.user.consumidor).data,
            status=status.HTTP_200_OK
        )


# ------------------------------------------------
# DOCUMENTOS DEL CONSUMIDOR AUTENTICADO
# ------------------------------------------------

class MisDocumentosView(APIView):
    """
    GET  /consumidores/me/documentos/ → ver documentos
    POST /consumidores/me/documentos/ → subir documento
    """

    permission_classes = [IsAuthenticated, IsConsumidor]

    def get(self, request):
        documentos = request.user.consumidor.documentos.all()
        serializer = DocumentoIdentidadSerializer(documentos, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        perfil = request.user.consumidor

        serializer = DocumentoIdentidadWriteSerializer(
            data=request.data,
            context={"perfil": perfil}
        )
        serializer.is_valid(raise_exception=True)
        documento = serializer.save(perfil=perfil)

        return Response(
            DocumentoIdentidadSerializer(documento).data,
            status=status.HTTP_201_CREATED
        )


# ------------------------------------------------
# GESTIÓN DE CONSUMIDORES (ANH)
# ------------------------------------------------

class ConsumidorPerfilViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    API para que ANH gestione perfiles de consumidores.

    Acciones:
      - list      : listar consumidores con filtros
      - retrieve  : ver perfil detallado
      - verificar : cambiar estado de identidad
      - alerta    : cambiar estado de alerta/bloqueo
    """

    permission_classes = [IsAuthenticated, IsAdminOrANH]

    # ------------------------------------------------
    # FILTROS
    # ------------------------------------------------

    filter_backends = [
        DjangoFilterBackend,
        OrderingFilter,
        SearchFilter,
    ]

    filterset_fields  = [
        "estado_identidad",
        "alerta_repetitividad",
        "actividad",
        "departamento",
        "municipio",
    ]
    ordering_fields   = ["fecha_creacion", "estado_identidad", "alerta_repetitividad"]
    ordering          = ["-fecha_creacion"]
    search_fields     = [
        "user__nombres",
        "user__apellido_paterno",
        "user__email",
        "documentos__numero_documento",
        "municipio__nombre",
    ]

    # ------------------------------------------------
    # QUERYSET
    # ------------------------------------------------

    def get_queryset(self):
        return ConsumidorPerfil.objects.select_related(
            "user",
            "departamento",
            "provincia",
            "municipio",
        ).prefetch_related("documentos")

    # ------------------------------------------------
    # SERIALIZER DINÁMICO
    # ------------------------------------------------

    def get_serializer_class(self):

        if self.action == "list":
            return ConsumidorPerfilListSerializer

        if self.action == "verificar":
            return CambiarEstadoIdentidadSerializer

        if self.action == "alerta":
            return CambiarAlertaSerializer

        return ConsumidorPerfilSerializer

    # ------------------------------------------------
    # VERIFICAR IDENTIDAD (ANH)
    # ------------------------------------------------

    @action(detail=True, methods=["post"])
    def verificar(self, request, pk=None):
        """
        Cambia el estado de identidad de un consumidor.
        Requiere observación cuando se rechaza.
        """
        perfil = self.get_object()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        estado_anterior = perfil.estado_identidad
        estado_nuevo    = serializer.validated_data["estado_identidad"]

        if estado_anterior == estado_nuevo:
            return Response(
                {
                    "detail": (
                        f"El consumidor ya se encuentra en estado "
                        f"{perfil.get_estado_identidad_display()}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            perfil.estado_identidad = estado_nuevo
            perfil.save(update_fields=["estado_identidad", "fecha_actualizacion"])

        return Response(
            ConsumidorPerfilSerializer(perfil).data,
            status=status.HTTP_200_OK
        )

    # ------------------------------------------------
    # CAMBIAR ALERTA DE REPETITIVIDAD (ANH)
    # ------------------------------------------------

    @action(detail=True, methods=["post"])
    def alerta(self, request, pk=None):
        """
        Permite a ANH cambiar el estado de alerta
        de un consumidor: NORMAL, EN_REVISION, BLOQUEADO.
        Requiere motivo cuando se bloquea.
        """
        perfil = self.get_object()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        alerta_anterior = perfil.alerta_repetitividad
        alerta_nueva    = serializer.validated_data["alerta_repetitividad"]
        motivo          = serializer.validated_data.get("motivo", "")

        if alerta_anterior == alerta_nueva:
            return Response(
                {
                    "detail": (
                        f"El consumidor ya tiene alerta en estado "
                        f"{perfil.get_alerta_repetitividad_display()}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        from django.utils import timezone

        with transaction.atomic():
            perfil.alerta_repetitividad = alerta_nueva
            perfil.motivo_bloqueo       = motivo

            # Registrar fecha solo cuando se marca alerta
            if alerta_nueva != ConsumidorPerfil.EstadoAlerta.NORMAL:
                perfil.fecha_alerta = timezone.now()
            else:
                perfil.fecha_alerta  = None
                perfil.motivo_bloqueo = ""

            perfil.save(update_fields=[
                "alerta_repetitividad",
                "fecha_alerta",
                "motivo_bloqueo",
                "fecha_actualizacion"
            ])

        # Notificar al consumidor por email
        from users.email_service import _enviar_email

        if alerta_nueva == ConsumidorPerfil.EstadoAlerta.BLOQUEADO:
            _enviar_email(
                asunto="Cuenta bloqueada — ANH",
                mensaje=(
                    f"Hola {perfil.user.nombres},\n\n"
                    f"Su cuenta ha sido bloqueada por la ANH.\n"
                    f"Motivo: {motivo}\n\n"
                    f"Comuníquese con la ANH para más información.\n\n"
                    f"Agencia Nacional de Hidrocarburos\nBolivia"
                ),
                destinatario=perfil.user.email
            )
        elif alerta_nueva == ConsumidorPerfil.EstadoAlerta.EN_REVISION:
            _enviar_email(
                asunto="Cuenta en revisión — ANH",
                mensaje=(
                    f"Hola {perfil.user.nombres},\n\n"
                    f"Su cuenta está siendo revisada por la ANH "
                    f"debido a actividad inusual en sus solicitudes.\n\n"
                    f"Comuníquese con la ANH para más información.\n\n"
                    f"Agencia Nacional de Hidrocarburos\nBolivia"
                ),
                destinatario=perfil.user.email
            )

        return Response(
            ConsumidorPerfilSerializer(perfil).data,
            status=status.HTTP_200_OK
        )

    # ------------------------------------------------
    # RESETEAR CONTRASEÑA (ADMIN/ANH)
    # ------------------------------------------------

    @action(detail=True, methods=["post"], url_path="resetear-password")
    def resetear_password(self, request, pk=None):
        """
        Resetea la contraseña de un consumidor por link: la actual queda
        inutilizable, se cierran sus sesiones y recibe un email para
        definir una nueva (services.resetear_password_por_link). Nadie
        ve la contraseña. Equivalente a
        FuncionarioResetearPasswordView, pero sobre ConsumidorPerfil:
        acá {pk} es el id del perfil, no del User, así que se opera
        sobre perfil.user.

        Sin restricción de auto-reset ni de ADMIN-only: el target acá
        siempre es un ConsumidorPerfil, nunca puede coincidir con la
        cuenta ANH/ADMIN que hace la request, y no hay riesgo de
        escalación de privilegios (un consumidor no tiene privilegios
        que escalar) — por eso alcanza con el IsAdminOrANH que ya
        gatea todo el viewset, a diferencia del ADMIN-only que usa la
        vía de funcionarios.

        No bloquea el reset si el consumidor tiene
        alerta_repetitividad=BLOQUEADO: ese bloqueo no impide el login
        (LoginSerializer no lo chequea, solo lo hace
        aprobar_solicitud()), así que resetear la contraseña no le
        devuelve ningún acceso que no tuviera ya. El frontend advierte
        igual sobre esto en el modal de confirmación.
        """

        perfil  = self.get_object()
        usuario = perfil.user

        # Todavía no creó su contraseña: corresponde reenviar el link
        # de activación (users/usuarios/<id>/reenviar-activacion/).
        if es_activacion_pendiente(usuario):
            return Response(
                {"detail": MENSAJE_RESET_CUENTA_PENDIENTE},
                status=status.HTTP_400_BAD_REQUEST
            )

        email_enviado = resetear_password_por_link(usuario)

        logger.warning(
            "Reset de contraseña: %s %s (id=%s) reseteó a consumidor %s (id=%s)",
            request.user.tipo_usuario, request.user.email, request.user.id,
            usuario.email, usuario.id,
        )

        return Response(
            {
                "detail":        "Contraseña reseteada. Se envió un enlace al consumidor.",
                "email":         usuario.email,
                "email_enviado": email_enviado,
            },
            status=status.HTTP_200_OK
        )