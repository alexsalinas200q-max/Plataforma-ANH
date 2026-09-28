# apps/users/permissions.py

from rest_framework.permissions import BasePermission
from .models import User


# ------------------------------------------------
# BASE
# Verificación completa de autenticación:
# activo, no suspendido, no bloqueado.
# Todos los permisos de rol heredan de aquí.
# ------------------------------------------------

class IsAuthenticatedActive(BasePermission):
    """
    Verifica que el usuario esté autenticado, activo,
    no suspendido y no bloqueado por intentos fallidos.
    Base para todos los permisos del sistema.
    """

    def has_permission(self, request, view):
        return (
            bool(request.user and request.user.is_authenticated)
            and request.user.is_active
            and request.user.estado_cuenta == User.EstadoCuenta.ACTIVO
            and not request.user.esta_bloqueado()
        )


# ------------------------------------------------
# PERMISO DINÁMICO POR ROL
# Extiende IsAuthenticatedActive para incluir
# verificación de bloqueo en todos los roles.
# ------------------------------------------------

class HasRole(IsAuthenticatedActive):
    """
    Permiso base dinámico por rol.
    Hereda todas las verificaciones de IsAuthenticatedActive
    y agrega validación de tipo de usuario.

    Uso:
        class MiPermiso(HasRole):
            allowed_roles = [User.TipoUsuario.ANH]
    """

    allowed_roles: list = []

    def has_permission(self, request, view):

        # Primero verificar autenticación y estado de cuenta
        if not super().has_permission(request, view):
            return False

        return request.user.tipo_usuario in self.allowed_roles


# ------------------------------------------------
# PERMISOS POR ROL
# ------------------------------------------------

class IsAdmin(HasRole):
    """Solo administradores del sistema."""
    allowed_roles = [User.TipoUsuario.ADMIN]


class IsANH(HasRole):
    """Solo personal ANH."""
    allowed_roles = [User.TipoUsuario.ANH]


class IsAdminOrANH(HasRole):
    """Administradores y personal ANH."""
    allowed_roles = [
        User.TipoUsuario.ADMIN,
        User.TipoUsuario.ANH,
    ]


class IsESS(HasRole):
    """Solo personal de estación de servicio."""
    allowed_roles = [User.TipoUsuario.ESS]


class IsConsumidor(HasRole):
    """
    Solo consumidores con perfil activo.
    Verifica además que el usuario tenga
    ConsumidorPerfil asociado.
    """
    allowed_roles = [User.TipoUsuario.CONS]

    def has_permission(self, request, view):

        if not super().has_permission(request, view):
            return False

        return hasattr(request.user, "consumidor")


class IsAdminOrANHOrESS(HasRole):
    """
    Cualquier funcionario institucional.
    Útil para vistas de solo lectura compartidas.
    """
    allowed_roles = [
        User.TipoUsuario.ADMIN,
        User.TipoUsuario.ANH,
        User.TipoUsuario.ESS,
    ]

# ------------------------------------------------
# PERMISOS CON NIVEL DE OBJETO
# ------------------------------------------------

class PuedeReenviarActivacion(IsAdminOrANH):
    """
    Reenvío del link de activación por staff.
    ADMIN puede reenviar a cualquier usuario; ANH solo a consumidores
    (mismo alcance que su registro de consumidores por admin).
    El objeto es el User destino — la view debe llamar a
    check_object_permissions().
    """

    def has_object_permission(self, request, view, obj):
        if request.user.tipo_usuario == User.TipoUsuario.ADMIN:
            return True
        return obj.tipo_usuario == User.TipoUsuario.CONS
