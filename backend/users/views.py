# apps/users/views.py
import os
import logging
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.conf import settings
from django.db import models

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status

from rest_framework_simplejwt.tokens import RefreshToken

from rest_framework.parsers import MultiPartParser, FormParser
from .serializers_admin import RegistroConsumidorPorAdminSerializer

from .models import User, TokenVerificacion

logger = logging.getLogger(__name__)
from .services import (
    MENSAJE_RESET_CUENTA_PENDIENTE,
    crear_token_verificacion,
    enviar_activacion,
    es_activacion_pendiente,
    resetear_password_por_link,
)
from .permissions import PuedeReenviarActivacion
from .email_service import (
    enviar_pin_verificacion,
    enviar_token_recuperacion,
)
from .serializers import (
    LoginSerializer,
    RegistroConsumidorSerializer,
    CrearFuncionarioSerializer,
    VerificarEmailSerializer,
    SolicitarRecuperacionSerializer,
    RecuperarPasswordSerializer,
    CambiarPasswordSerializer,
    CambiarPasswordObligatorioSerializer,
    UserSerializer,
)


# ------------------------------------------------
# HELPERS
# ------------------------------------------------

def _set_auth_cookies(response, access: str, refresh: str) -> None:
    """
    Setea las cookies httponly con access y refresh tokens.
    Lee samesite y secure desde settings.SIMPLE_JWT para que
    funcione cross-origin en producción (Vercel ↔ Railway).
    """
    samesite = settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax")
    secure   = settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", not settings.DEBUG)

    response.set_cookie(
        key="access_token",
        value=access,
        httponly=True,
        secure=secure,
        samesite=samesite,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh,
        httponly=True,
        secure=secure,
        samesite=samesite,
    )


def _clear_auth_cookies(response) -> None:
    """
    Elimina las cookies de autenticación.
    Usa los mismos atributos que _set_auth_cookies
    para garantizar que el navegador las elimine correctamente.
    """
    samesite = settings.SIMPLE_JWT.get("AUTH_COOKIE_SAMESITE", "Lax")
    secure   = settings.SIMPLE_JWT.get("AUTH_COOKIE_SECURE", not settings.DEBUG)

    response.delete_cookie("access_token",  samesite=samesite)
    response.delete_cookie("refresh_token", samesite=samesite)


# ------------------------------------------------
# REGISTRO DE CONSUMIDOR
# ------------------------------------------------

class RegistroConsumidorView(APIView):
    """
    Registro público de consumidores desde el frontend.
    Crea User (CONS) + ConsumidorPerfil en una transacción.
    El estado queda PENDIENTE hasta verificar email.
    """

    permission_classes = [AllowAny]

    def post(self, request):

        serializer = RegistroConsumidorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = serializer.save()
        except IntegrityError:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                {"email": "Ya existe una cuenta registrada con este correo."}
            )

        # Generar y enviar PIN de verificación de email
        token = crear_token_verificacion(
            user=user,
            tipo=TokenVerificacion.TipoToken.VERIFICACION_EMAIL
        )

        enviar_pin_verificacion(user=user, pin=token.codigo_pin)

        return Response(
            {
                "detail": (
                    "Registro exitoso. Revise su correo para "
                    "verificar su cuenta."
                ),
                "email": user.email,
            },
            status=status.HTTP_201_CREATED
        )


# ------------------------------------------------
# CREAR FUNCIONARIO (ADMIN)
# ------------------------------------------------

class CrearFuncionarioView(APIView):
    """
    Creación de funcionarios ADMIN, ANH y ESS.
    Solo accesible por administradores del sistema.
    Crea User + PerfilFuncionario en un solo paso.

    La cuenta nace PENDIENTE y sin contraseña: el funcionario la
    define desde el link de activación que se le envía por email.
    El administrador nunca conoce su contraseña.
    """

    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        return [IsAuthenticated()]

    def post(self, request):

        # Solo ADMIN puede crear funcionarios
        if request.user.tipo_usuario != User.TipoUsuario.ADMIN:
            return Response(
                {"detail": "Solo los administradores pueden crear funcionarios."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CrearFuncionarioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = serializer.save()
        except IntegrityError:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                {"email": "Ya existe un funcionario registrado con este correo o documento."}
            )

        # Fuera del atomic de serializer.create(): si la creación se
        # revirtiera, no debe quedar un email enviado.
        email_enviado = enviar_activacion(user)

        return Response(
            {
                "detail":        "Funcionario creado exitosamente.",
                "user_id":       user.id,
                "email":         user.email,
                "tipo_usuario":  user.tipo_usuario,
                "email_enviado": email_enviado,
            },
            status=status.HTTP_201_CREATED
        )


# ------------------------------------------------
# LOGIN
# ------------------------------------------------

class LoginView(APIView):
    """
    Autenticación por email y contraseña.
    Retorna tokens JWT como cookies httponly Y en el body
    de la respuesta (campo "access") para que el frontend
    pueda usarlo como header Authorization Bearer en casos
    donde las cookies cross-origin fallan (Safari iOS, etc).
    Registra intentos fallidos y bloquea tras 5 intentos.
    """

    permission_classes = [AllowAny]

    def post(self, request):

        serializer = LoginSerializer(
            data=request.data,
            context={"request": request}
        )

        if not serializer.is_valid():
            # Registrar intento fallido si el usuario existe.
            # CRÍTICO: sin normalizar+iexact acá, esto es un bypass
            # completo del bloqueo por fuerza bruta. LoginSerializer
            # normaliza el email antes de autenticar, así que el login
            # se resuelve igual contra el usuario correcto — pero como
            # este lookup usaba el valor crudo con match exacto, un
            # atacante que varía las mayúsculas del email en cada
            # intento (Admin@x.com, ADMIN@x.com, aDmIn@x.com...) nunca
            # encontraba al usuario acá, intentos_fallidos nunca subía,
            # y la cuenta nunca se bloqueaba, sin importar cuántas
            # contraseñas se probaran. Encontrado en la auditoría de
            # 2026-09, no reportado originalmente.
            email = request.data.get("email", "").lower().strip()
            try:
                user = User.objects.get(email__iexact=email)
                from configuracion.models import ConfiguracionSistema
                config = ConfiguracionSistema.obtener()

                user.intentos_fallidos += 1

                # Bloquear tras superar el máximo configurado
                if user.intentos_fallidos >= config.max_intentos_fallidos:
                    user.bloqueado_hasta = timezone.now() + timezone.timedelta(
                        minutes=config.tiempo_bloqueo_minutos
                    )

                user.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
            except User.DoesNotExist:
                pass

            # El único code que se expone es email_no_verificado (solo
            # posible con la contraseña correcta, ver LoginSerializer):
            # el frontend lo usa para redirigir a /verificar-email. El
            # resto de los errores viaja sin code, así una cuenta
            # pendiente de activación es indistinguible de unas
            # credenciales inválidas.
            body = dict(serializer.errors)
            errores = serializer.errors.get("non_field_errors", [])
            if errores and getattr(errores[0], "code", None) == "email_no_verificado":
                body["code"] = "email_no_verificado"

            return Response(body, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data["user"]

        # Resetear intentos fallidos tras login exitoso
        if user.intentos_fallidos > 0:
            user.intentos_fallidos = 0
            user.bloqueado_hasta = None
            user.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])

        # Generar tokens JWT
        refresh = RefreshToken.for_user(user)
        access  = str(refresh.access_token)

        # authenticate() no aplica select_related: se vuelve a traer con
        # el perfil precargado para que UserSerializer no dispare una
        # query extra al resolver perfil_funcionario (mismo caso que
        # MiPerfilView).
        user_completo = User.objects.select_related(
            "perfil_funcionario__estacion_servicio"
        ).get(pk=user.pk)

        # IMPORTANTE: enviar access en el body para que el frontend
        # lo use como Authorization Bearer si las cookies fallan
        response = Response(
            {
                "detail": "Login exitoso.",
                "user": UserSerializer(user_completo).data,
                "access": access,
            },
            status=status.HTTP_200_OK
        )

        _set_auth_cookies(response, access=access, refresh=str(refresh))

        return response


# ------------------------------------------------
# REFRESH TOKEN
# ------------------------------------------------

class RefreshView(APIView):
    """
    Renueva el access token usando el refresh token
    almacenado en las cookies. También devuelve el nuevo
    access en el body para que el frontend pueda actualizar
    su header Authorization Bearer.
    """

    permission_classes = [AllowAny]

    def post(self, request):

        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"detail": "Token no encontrado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            refresh = RefreshToken(refresh_token)
            access  = str(refresh.access_token)

            # IMPORTANTE: enviar access también en el body
            response = Response(
                {
                    "detail": "Token renovado.",
                    "access": access,
                },
                status=status.HTTP_200_OK
            )
            _set_auth_cookies(response, access=access, refresh=refresh_token)
            return response

        except Exception:
            return Response(
                {"detail": "Token inválido o expirado."},
                status=status.HTTP_400_BAD_REQUEST
            )


# ------------------------------------------------
# LOGOUT
# ------------------------------------------------

class LogoutView(APIView):
    """
    Cierra la sesión del usuario autenticado.
    Invalida el refresh token y elimina las cookies.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):

        refresh_token = request.COOKIES.get("refresh_token")

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                # Si el token ya es inválido, igual limpiamos cookies
                pass

        response = Response(
            {"detail": "Logout exitoso."},
            status=status.HTTP_200_OK
        )
        _clear_auth_cookies(response)
        return response


# ------------------------------------------------
# VERIFICAR EMAIL POR PIN
# ------------------------------------------------

class VerificarEmailView(APIView):
    """
    Verifica el email del consumidor mediante un PIN
    de 6 dígitos enviado por correo electrónico.
    La validación completa se delega al serializer.
    """

    permission_classes = [AllowAny]

    def post(self, request):

        serializer = VerificarEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user  = serializer.validated_data["user"]
        token = serializer.validated_data["token"]

        with transaction.atomic():
            user.email_verificado = True
            user.estado_cuenta    = User.EstadoCuenta.ACTIVO
            user.save(update_fields=["email_verificado", "estado_cuenta"])

            token.usado = True
            token.save(update_fields=["usado"])

        return Response(
            {"detail": "Correo verificado correctamente."},
            status=status.HTTP_200_OK
        )


# ------------------------------------------------
# SOLICITAR RECUPERACIÓN DE CONTRASEÑA
# ------------------------------------------------

class SolicitarRecuperacionView(APIView):
    """
    Recibe el email y envía un token de recuperación
    si el usuario existe. Siempre responde con éxito
    para no revelar si el email está registrado.
    """

    permission_classes = [AllowAny]

    def post(self, request):

        serializer = SolicitarRecuperacionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email__iexact=email)

            # Generar token de recuperación
            # (invalida anteriores internamente)
            token = crear_token_verificacion(
                user=user,
                tipo=TokenVerificacion.TipoToken.RECUPERACION_PASSWORD
            )

            enviar_token_recuperacion(user=user, token_uuid=str(token.token))

        except User.DoesNotExist:
            # No revelamos si el email existe
            pass

        return Response(
            {
                "detail": (
                    "Si el correo está registrado, recibirá "
                    "las instrucciones para recuperar su contraseña."
                )
            },
            status=status.HTTP_200_OK
        )


# ------------------------------------------------
# RECUPERAR CONTRASEÑA (CON TOKEN)
# ------------------------------------------------

class RecuperarPasswordView(APIView):
    """
    Permite cambiar la contraseña usando el token
    de recuperación recibido por correo.

    Sirve también para la activación de cuentas creadas por admin
    (mismo tipo de token RECUP): si la cuenta está PENDIENTE, completar
    el link la deja ACTIVO y con el email verificado — el usuario
    demostró que controla el correo. Una cuenta SUSPENDIDO cambia la
    contraseña pero sigue suspendida. No blacklistea sesiones: en la
    activación no hay sesiones previas, y en la recuperación el reset
    por admin ya las cerró.
    """

    permission_classes = [AllowAny]

    def post(self, request):

        serializer = RecuperarPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_obj    = serializer.validated_data["token_obj"]
        password_nuevo = serializer.validated_data["password"]

        with transaction.atomic():
            user = token_obj.user
            user.set_password(password_nuevo)
            user.requiere_cambio_password = False
            campos = ["password", "requiere_cambio_password"]

            activada = user.estado_cuenta == User.EstadoCuenta.PENDIENTE
            if activada:
                user.estado_cuenta    = User.EstadoCuenta.ACTIVO
                user.email_verificado = True
                campos += ["estado_cuenta", "email_verificado"]

            user.save(update_fields=campos)

            token_obj.usado = True
            token_obj.save(update_fields=["usado"])

        return Response(
            {
                "detail": (
                    "Cuenta activada correctamente." if activada
                    else "Contraseña actualizada correctamente."
                )
            },
            status=status.HTTP_200_OK
        )


# ------------------------------------------------
# CAMBIAR CONTRASEÑA (USUARIO AUTENTICADO)
# ------------------------------------------------

class CambiarPasswordView(APIView):
    """
    Permite al usuario autenticado cambiar su contraseña
    conociendo la actual. Para el caso requiere_cambio_password=True
    (contraseña generada por un admin) usar CambiarPasswordObligatorioView,
    que no exige la contraseña actual.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = CambiarPasswordSerializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data["password_nuevo"])
        user.requiere_cambio_password = False
        user.save(update_fields=["password", "requiere_cambio_password"])

        # Invalidar sesión actual para forzar nuevo login
        response = Response(
            {
                "detail": (
                    "Contraseña actualizada. "
                    "Por favor inicie sesión nuevamente."
                )
            },
            status=status.HTTP_200_OK
        )
        _clear_auth_cookies(response)
        return response


class CambiarPasswordObligatorioView(APIView):
    """
    Cambio de contraseña forzado cuando requiere_cambio_password=True
    (contraseña generada por un admin: alta de funcionario, registro
    de consumidor por admin, o reset de contraseña). No exige la
    contraseña actual porque el usuario acaba de autenticarse con
    ella — pedírsela de nuevo es fricción sin valor de seguridad.

    A diferencia de CambiarPasswordView, esta vista NO limpia las
    cookies de sesión: SIMPLE_JWT no tiene CHECK_REVOKE_TOKEN activo,
    así que la validez del access/refresh token no depende del hash
    de la contraseña, y forzar un nuevo login inmediatamente después
    de que el usuario acaba de iniciar sesión sería mala experiencia
    sin beneficio real.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):

        if not request.user.requiere_cambio_password:
            return Response(
                {"detail": "Esta cuenta no requiere cambio de contraseña obligatorio."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CambiarPasswordObligatorioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data["password_nuevo"])
        user.requiere_cambio_password = False
        user.save(update_fields=["password", "requiere_cambio_password"])

        return Response(
            {"detail": "Contraseña actualizada correctamente."},
            status=status.HTTP_200_OK
        )


# ------------------------------------------------
# REENVIAR PIN DE VERIFICACIÓN
# ------------------------------------------------

class ReenviarPinView(APIView):
    """
    Permite al usuario solicitar un nuevo PIN
    si no pudo verificar su cuenta por email.
    Solo funciona si la cuenta no está verificada.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email", "").lower().strip()

        if not email:
            return Response(
                {"detail": "El email es requerido."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "Si el correo está registrado y no verificado, recibirás un nuevo PIN."},
                status=status.HTTP_200_OK
            )

        if user.email_verificado:
            return Response(
                {"detail": "Esta cuenta ya está verificada. Inicia sesión normalmente."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Cuenta creada por admin: se activa con el link, no con PIN.
        # Verificarla por PIN la dejaría ACTIVO sin contraseña usable.
        # Misma respuesta que un email inexistente.
        if es_activacion_pendiente(user):
            return Response(
                {"detail": "Si el correo está registrado y no verificado, recibirás un nuevo PIN."},
                status=status.HTTP_200_OK
            )

        # Invalidar PINs anteriores y generar uno nuevo
        TokenVerificacion.objects.filter(
            user=user,
            tipo=TokenVerificacion.TipoToken.VERIFICACION_EMAIL,
            usado=False,
        ).update(usado=True)

        token = crear_token_verificacion(
            user=user,
            tipo=TokenVerificacion.TipoToken.VERIFICACION_EMAIL
        )
        enviar_pin_verificacion(user=user, pin=token.codigo_pin)

        return Response(
            {"detail": "Se envió un nuevo PIN a tu correo electrónico."},
            status=status.HTTP_200_OK
        )


# ------------------------------------------------
# PERFIL DEL USUARIO AUTENTICADO
# ------------------------------------------------

class MiPerfilView(APIView):
    """
    Retorna los datos del usuario autenticado.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # select_related evita una query extra para perfil_funcionario
        # (UserSerializer la resuelve con hasattr/acceso lazy) en un
        # endpoint que el frontend llama en casi cada carga de página.
        user = User.objects.select_related(
            "perfil_funcionario__estacion_servicio"
        ).get(pk=request.user.pk)
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_200_OK
        )


# ------------------------------------------------
# GESTIÓN DE FUNCIONARIOS
# ------------------------------------------------

class FuncionarioListView(APIView):
    """
    Lista todos los funcionarios del sistema.
    ADMIN puede ver ANH, ESS y ADMIN.
    ANH puede ver solo ESS.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.tipo_usuario not in ["ADMIN", "ANH"]:
            return Response(
                {"detail": "No tienes permiso para ver funcionarios."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Filtrar por tipo si se especifica
        tipo = request.query_params.get("tipo_usuario", None)
        search = request.query_params.get("search", "")

        qs = User.objects.exclude(
            tipo_usuario=User.TipoUsuario.CONS
        ).select_related("perfil_funcionario__estacion_servicio")

        # ANH solo puede ver ESS
        if user.tipo_usuario == "ANH":
            qs = qs.filter(tipo_usuario=User.TipoUsuario.ESS)

        if tipo:
            qs = qs.filter(tipo_usuario=tipo)

        if search:
            qs = qs.filter(
                models.Q(nombres__icontains=search) |
                models.Q(apellido_paterno__icontains=search) |
                models.Q(email__icontains=search)
            )

        data = []
        for u in qs:
            perfil = getattr(u, "perfil_funcionario", None)
            data.append({
                "id":               u.id,
                "email":            u.email,
                "nombres":          u.nombres,
                "apellido_paterno": u.apellido_paterno,
                "apellido_materno": u.apellido_materno,
                "nombre_completo":  u.nombre_completo(),
                "tipo_usuario":     u.tipo_usuario,
                "estado_cuenta":    u.estado_cuenta,
                "email_verificado": u.email_verificado,
                "date_joined":      u.date_joined.isoformat(),
                "perfil": {
                    "id":                   perfil.id if perfil else None,
                    "cargo":                perfil.cargo if perfil else "",
                    "unidad_departamento":  perfil.unidad_departamento if perfil else "",
                    "numero_funcionario":   perfil.numero_funcionario if perfil else "",
                    "numero_documento":     perfil.numero_documento if perfil else "",
                    "tipo_documento":       perfil.tipo_documento if perfil else "",
                    "celular":              perfil.celular if perfil else "",
                    "estacion_servicio_id": perfil.estacion_servicio_id if perfil else None,
                    "estacion_nombre":      perfil.estacion_servicio.nombre if perfil and perfil.estacion_servicio else None,
                } if perfil else None,
            })

        return Response(data, status=status.HTTP_200_OK)


class FuncionarioDetailView(APIView):
    """
    Detalle y edición de un funcionario.
    Acepta PUT y PATCH: el update es parcial en ambos casos, ya que
    cada campo usa data.get() con fallback al valor actual.
    """
    permission_classes = [IsAuthenticated]

    def _get_usuario(self, user_id, request_user):
        try:
            u = User.objects.select_related(
                "perfil_funcionario__estacion_servicio"
            ).get(id=user_id)
        except User.DoesNotExist:
            return None

        # ANH solo puede ver ESS
        if request_user.tipo_usuario == "ANH" and u.tipo_usuario != "ESS":
            return None

        # ANH no puede ver otros ANH ni ADMIN
        if request_user.tipo_usuario not in ["ADMIN", "ANH"]:
            return None

        return u

    def get(self, request, user_id):
        u = self._get_usuario(user_id, request.user)
        if not u:
            return Response({"detail": "No encontrado."}, status=status.HTTP_404_NOT_FOUND)

        perfil = getattr(u, "perfil_funcionario", None)
        return Response({
            "id":               u.id,
            "email":            u.email,
            "nombres":          u.nombres,
            "apellido_paterno": u.apellido_paterno,
            "apellido_materno": u.apellido_materno,
            "tipo_usuario":     u.tipo_usuario,
            "estado_cuenta":    u.estado_cuenta,
            "email_verificado": u.email_verificado,
            "date_joined":      u.date_joined.isoformat(),
            "perfil": {
                "id":                   perfil.id if perfil else None,
                "cargo":                perfil.cargo if perfil else "",
                "unidad_departamento":  perfil.unidad_departamento if perfil else "",
                "numero_funcionario":   perfil.numero_funcionario if perfil else "",
                "numero_documento":     perfil.numero_documento if perfil else "",
                "tipo_documento":       perfil.tipo_documento if perfil else "",
                "celular":              perfil.celular if perfil else "",
                "estacion_servicio_id": perfil.estacion_servicio_id if perfil else None,
                "estacion_nombre":      perfil.estacion_servicio.nombre if perfil and perfil.estacion_servicio else None,
            } if perfil else None,
        })

    def put(self, request, user_id):
        u = self._get_usuario(user_id, request.user)
        if not u:
            return Response({"detail": "No encontrado."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data

        # Actualizar datos básicos del usuario
        u.nombres          = data.get("nombres", u.nombres)
        u.apellido_paterno = data.get("apellido_paterno", u.apellido_paterno)
        u.apellido_materno = data.get("apellido_materno", u.apellido_materno)
        u.save(update_fields=["nombres", "apellido_paterno", "apellido_materno"])

        # Actualizar perfil funcionario
        perfil = getattr(u, "perfil_funcionario", None)
        if perfil:
            perfil.cargo               = data.get("cargo", perfil.cargo)
            perfil.unidad_departamento = data.get("unidad_departamento", perfil.unidad_departamento)
            perfil.celular             = data.get("celular", perfil.celular)

            # Estos tres se mostraban en el formulario de edición pero
            # se ignoraban al guardar: el usuario creía haberlos cambiado.
            perfil.numero_funcionario  = data.get("numero_funcionario", perfil.numero_funcionario)
            perfil.tipo_documento      = data.get("tipo_documento", perfil.tipo_documento)
            perfil.numero_documento    = data.get("numero_documento", perfil.numero_documento)

            # Actualizar estacion solo para ESS
            if u.tipo_usuario == "ESS" and "estacion_servicio_id" in data:
                from estaciones.models import EstacionServicio
                try:
                    est = EstacionServicio.objects.get(id=data["estacion_servicio_id"])
                    perfil.estacion_servicio = est
                except EstacionServicio.DoesNotExist:
                    return Response(
                        {"detail": "Estación no encontrada."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # numero_documento y numero_funcionario son unique en el modelo:
            # sin este manejo un duplicado devolvería un 500.
            try:
                perfil.save()
            except IntegrityError:
                return Response(
                    {"detail": "El número de documento o de funcionario ya está en uso."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response({"detail": "Funcionario actualizado correctamente."})

    def patch(self, request, user_id):
        # El update ya es parcial por diseño (data.get con fallback),
        # así que PATCH y PUT comparten implementación.
        return self.put(request, user_id)


class FuncionarioCambiarEstadoView(APIView):
    """
    Activa o suspende un funcionario.
    Solo ADMIN puede cambiar estado de cualquier funcionario.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        if request.user.tipo_usuario != "ADMIN":
            return Response(
                {"detail": "Solo el administrador puede cambiar el estado de un funcionario."},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            u = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": "No encontrado."}, status=status.HTTP_404_NOT_FOUND)

        # Una cuenta pendiente se activa solo con el link (define su
        # contraseña y verifica el email). Activarla a mano la dejaría
        # ACTIVO sin contraseña; suspenderla la sacaría del reenvío.
        if u.estado_cuenta == User.EstadoCuenta.PENDIENTE:
            return Response(
                {
                    "detail": (
                        "La cuenta aún no fue activada por el usuario. "
                        "Reenvía el enlace de activación."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        nuevo_estado = request.data.get("estado_cuenta")
        if nuevo_estado not in [
            User.EstadoCuenta.ACTIVO,
            User.EstadoCuenta.SUSPENDIDO,
        ]:
            return Response(
                {"detail": "Estado inválido. Use ACTIVO o SUSPENDIDO."},
                status=status.HTTP_400_BAD_REQUEST
            )

        u.estado_cuenta = nuevo_estado
        u.save(update_fields=["estado_cuenta"])

        return Response({
            "detail": f"Estado cambiado a {nuevo_estado}.",
            "estado_cuenta": nuevo_estado,
        })


class FuncionarioResetearPasswordView(APIView):
    """
    Resetea la contraseña de un funcionario (ADMIN/ANH/ESS) por link.

    Solo ADMIN puede usarlo, y no puede resetear su propia contraseña
    por esta vía (para eso está el cambio normal con contraseña actual,
    en CambiarPasswordView). La contraseña actual queda inutilizable,
    se cierran las sesiones y el usuario recibe un link para definir
    una nueva (ver services.resetear_password_por_link). Nadie ve la
    contraseña.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        if request.user.tipo_usuario != "ADMIN":
            return Response(
                {"detail": "Solo el administrador puede resetear contraseñas."},
                status=status.HTTP_403_FORBIDDEN
            )

        if request.user.id == user_id:
            return Response(
                {
                    "detail": (
                        "No puedes resetear tu propia contraseña por esta vía. "
                        "Usa el cambio de contraseña habitual."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            usuario = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": "No encontrado."}, status=status.HTTP_404_NOT_FOUND)

        # Todavía no creó su contraseña: lo que corresponde es reenviar
        # el link de activación, no resetear.
        if es_activacion_pendiente(usuario):
            return Response(
                {"detail": MENSAJE_RESET_CUENTA_PENDIENTE},
                status=status.HTTP_400_BAD_REQUEST
            )

        email_enviado = resetear_password_por_link(usuario)

        # Acción sensible sobre la cuenta de otro usuario: sin un sistema
        # de auditoría todavía, al menos queda registrada en los logs.
        logger.warning(
            "Reset de contraseña: admin %s (id=%s) reseteó a %s (id=%s)",
            request.user.email, request.user.id, usuario.email, usuario.id,
        )

        return Response(
            {
                "detail":        "Contraseña reseteada. Se envió un enlace al usuario.",
                "email":         usuario.email,
                "email_enviado": email_enviado,
            },
            status=status.HTTP_200_OK
        )


# ------------------------------------------------
# REGISTRO DE CONSUMIDOR POR ADMIN
# ------------------------------------------------

class RegistroConsumidorPorAdminView(APIView):
    """
    POST /api/users/registro/consumidor-por-admin/

    Registra a un consumidor iniciado por un funcionario ANH o ADMIN
    (típicamente en atención presencial).

    A diferencia del auto-registro público:
      - Nadie elige contraseña al crear la cuenta: el consumidor la
        define desde el link de activación que recibe por email
      - No se envía PIN: completar el link verifica el email
      - La cuenta queda PENDIENTE hasta que el consumidor usa el link

    Solo usuarios ANH o ADMIN autenticados pueden llamar este endpoint.
    """

    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):

        # Solo ANH y ADMIN pueden registrar consumidores por esta vía.
        if request.user.tipo_usuario not in ("ANH", "ADMIN"):
            return Response(
                {"detail": "Solo ANH o ADMIN pueden registrar consumidores."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RegistroConsumidorPorAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Fuera del atomic de serializer.create() (ver CrearFuncionarioView).
        email_enviado = enviar_activacion(user)

        return Response(
            {
                "message":       "Consumidor registrado correctamente",
                "user_id":       user.id,
                "email":         user.email,
                "email_enviado": email_enviado,
            },
            status=status.HTTP_201_CREATED,
        )


# ------------------------------------------------
# REENVÍO DEL LINK DE ACTIVACIÓN
# ------------------------------------------------

class ReenviarActivacionView(APIView):
    """
    POST /api/users/auth/reenviar-activacion/   body: {email}

    Reenvío público (desde el login). Si el email corresponde a una
    cuenta pendiente de activación, invalida los links anteriores y
    envía uno nuevo. Responde siempre lo mismo, exista o no el email,
    para no revelar qué cuentas existen ni en qué estado están.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email", "")
        email = email.lower().strip() if isinstance(email, str) else ""

        user = User.objects.filter(email__iexact=email).first() if email else None
        if user and es_activacion_pendiente(user):
            enviar_activacion(user)

        return Response(
            {
                "detail": (
                    "Si el correo corresponde a una cuenta pendiente de "
                    "activación, recibirás un nuevo enlace en los próximos minutos."
                )
            },
            status=status.HTTP_200_OK
        )


class ReenviarActivacionStaffView(APIView):
    """
    POST /api/users/usuarios/<user_id>/reenviar-activacion/

    Reenvío desde el panel. ADMIN a cualquier usuario, ANH solo a
    consumidores (PuedeReenviarActivacion). A diferencia del reenvío
    público, acá sí se informa el resultado: quien llama ya ve el
    estado de la cuenta en el panel.
    """

    permission_classes = [PuedeReenviarActivacion]

    def post(self, request, user_id):
        try:
            usuario = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"detail": "No encontrado."}, status=status.HTTP_404_NOT_FOUND)

        self.check_object_permissions(request, usuario)

        if not es_activacion_pendiente(usuario):
            return Response(
                {"detail": "Esta cuenta no está pendiente de activación."},
                status=status.HTTP_400_BAD_REQUEST
            )

        email_enviado = enviar_activacion(usuario)

        return Response(
            {
                "detail":        "Se envió un nuevo enlace de activación.",
                "email":         usuario.email,
                "email_enviado": email_enviado,
            },
            status=status.HTTP_200_OK
        )
