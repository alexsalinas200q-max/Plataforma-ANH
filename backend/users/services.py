# apps/users/services.py

import secrets
from datetime import timedelta

from django.utils import timezone

from .models import TokenVerificacion


# Validez del link de activación de cuentas creadas por ADMIN/ANH.
# Más largo que el de recuperación (ConfiguracionSistema, 1 h por
# defecto): el usuario no pidió este email y puede leerlo días
# después. Constante en código a propósito — no es algo que el
# administrador necesite ajustar.
HORAS_EXPIRACION_ACTIVACION = 72


# ------------------------------------------------
# SERVICIO: CREAR TOKEN DE VERIFICACIÓN
# ------------------------------------------------

def crear_token_verificacion(user, tipo: str, horas: int | None = None) -> TokenVerificacion:
    """
    Crea un token de verificación de un solo uso.

    - Invalida tokens anteriores del mismo tipo.
    - Genera un PIN de 6 dígitos criptográficamente seguro.
    - La expiración se lee desde ConfiguracionSistema
      para que el administrador pueda ajustarla sin
      tocar código. `horas` la reemplaza (usado por el
      link de activación, ver HORAS_EXPIRACION_ACTIVACION).

    Retorna el objeto TokenVerificacion creado.
    El PIN está disponible en token.codigo_pin.
    """

    # Import tardío para evitar circular imports
    from configuracion.models import ConfiguracionSistema

    config = ConfiguracionSistema.obtener()

    # Invalidar tokens anteriores del mismo tipo
    TokenVerificacion.objects.filter(
        user=user,
        tipo=tipo,
        usado=False,
    ).update(usado=True)

    # Generar PIN criptográficamente seguro
    pin = str(secrets.randbelow(900000) + 100000)

    # Calcular expiración según tipo y configuración
    if horas is not None:
        expiracion = timezone.now() + timedelta(hours=horas)
    elif tipo == TokenVerificacion.TipoToken.VERIFICACION_EMAIL:
        expiracion = timezone.now() + timedelta(
            minutes=config.tiempo_expiracion_pin_minutos
        )
    else:
        expiracion = timezone.now() + timedelta(
            hours=config.tiempo_expiracion_token_recuperacion_horas
        )

    return TokenVerificacion.objects.create(
        user             = user,
        tipo             = tipo,
        codigo_pin       = pin,
        fecha_expiracion = expiracion,
    )


# ------------------------------------------------
# ACTIVACIÓN DE CUENTA POR LINK
# Cuentas creadas por ADMIN/ANH: nacen PENDIENTE y sin contraseña
# usable; el usuario define la suya desde el link del email.
# ------------------------------------------------

def es_activacion_pendiente(user) -> bool:
    """
    True si la cuenta fue creada por un administrador y el usuario
    todavía no definió su contraseña.

    No depende de que exista un token vigente (el link vence a las
    72 h): una cuenta del registro público siempre tiene contraseña
    usable, así que la combinación PENDIENTE + contraseña inutilizable
    solo se da en el alta por admin.
    """
    from .models import User

    return (
        user.estado_cuenta == User.EstadoCuenta.PENDIENTE
        and not user.has_usable_password()
    )


def enviar_activacion(user) -> bool:
    """
    Genera un token RECUP de 72 h (invalida los anteriores) y envía
    el link de activación. Retorna si el email salió.

    Llamar FUERA de transaction.atomic: si la transacción se revierte
    no debe quedar un email enviado con un token que no existe.
    """
    from .email_service import enviar_link_activacion

    token = crear_token_verificacion(
        user  = user,
        tipo  = TokenVerificacion.TipoToken.RECUPERACION_PASSWORD,
        horas = HORAS_EXPIRACION_ACTIVACION,
    )
    return enviar_link_activacion(user=user, token_uuid=str(token.token))


# ------------------------------------------------
# RESET DE CONTRASEÑA INICIADO POR ADMIN/ANH
# ------------------------------------------------

# Respuesta 400 de los dos endpoints de reset (funcionarios y
# consumidores) cuando la cuenta todavía no fue activada.
MENSAJE_RESET_CUENTA_PENDIENTE = (
    "La cuenta está pendiente de activación. "
    "Usa reenviar enlace de activación."
)

def resetear_password_por_link(user) -> bool:
    """
    Reset iniciado por staff (funcionarios o consumidores):

      - Deja la contraseña actual inutilizable de inmediato (útil si la
        cuenta fue comprometida: la clave vieja deja de servir ya).
      - Cierra las sesiones activas blacklisteando todos los refresh
        tokens outstanding. LIMITACIÓN CONOCIDA Y ACEPTADA: no revoca el
        access token que el usuario ya tenga en memoria, que sigue
        válido hasta su expiración (máx. 30 min, ACCESS_TOKEN_LIFETIME)
        — misma ventana que el logout normal.
      - Envía un link de recuperación (token RECUP con la expiración de
        ConfiguracionSistema). Si vence, el usuario usa la recuperación
        pública, que acepta cuentas con contraseña inutilizable.

    El estado de la cuenta no cambia. Retorna si el email salió.
    """
    from rest_framework_simplejwt.token_blacklist.models import (
        OutstandingToken, BlacklistedToken,
    )
    from .email_service import enviar_token_recuperacion

    user.set_unusable_password()
    user.requiere_cambio_password = False
    user.save(update_fields=["password", "requiere_cambio_password"])

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)

    token = crear_token_verificacion(
        user = user,
        tipo = TokenVerificacion.TipoToken.RECUPERACION_PASSWORD,
    )
    return enviar_token_recuperacion(
        user=user, token_uuid=str(token.token), por_admin=True,
    )
