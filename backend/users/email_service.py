# apps/users/email_service.py

import logging
import requests

from core.fechas import formatear_fecha_hora

from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)

# Dominio de las cuentas de demostración (seed_demo). No es un dominio
# real: a estas direcciones no se les envía nada.
DOMINIO_DEMO = "@demo.anh.bo"


# ------------------------------------------------
# HELPER INTERNO
# ------------------------------------------------

def _enviar_email(
    asunto: str,
    mensaje: str,
    destinatario: str,
) -> bool:
    """
    Envía un email y captura errores sin romper el flujo principal.

    Estrategia:
      - Si BREVO_API_KEY está configurada, usa la API HTTP de Brevo
        (Railway no bloquea HTTPS saliente).
      - Si no está configurada, hace fallback a Django send_mail
        (que en desarrollo escribe a consola).

    Retorna True si el envío fue exitoso. Las direcciones de demo
    (DOMINIO_DEMO) se omiten sin enviar y cuentan como exitosas, para
    que la UI no muestre "no se pudo enviar" durante una demostración.
    """
    if destinatario.lower().endswith(DOMINIO_DEMO):
        logger.info(f"Email a {destinatario} omitido (cuenta de demo) — asunto: {asunto}")
        return True

    api_key = getattr(settings, "BREVO_API_KEY", "")

    # Sin API key → fallback a Django send_mail (desarrollo)
    if not api_key:
        try:
            send_mail(
                subject        = asunto,
                message        = mensaje,
                from_email     = settings.DEFAULT_FROM_EMAIL,
                recipient_list = [destinatario],
                fail_silently  = False,
            )
            logger.info(f"Email enviado a {destinatario} (Django backend)")
            return True
        except Exception as e:
            logger.error(
                f"Error al enviar email a {destinatario} "
                f"— asunto: {asunto} — error: {e}"
            )
            return False

    # Producción: Brevo HTTP API
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers = {
                "accept":       "application/json",
                "api-key":      api_key,
                "content-type": "application/json",
            },
            json = {
                "sender": {
                    "name":  getattr(settings, "BREVO_SENDER_NAME",  "ANH Bolivia"),
                    "email": settings.BREVO_SENDER_EMAIL,
                },
                "to":          [{"email": destinatario}],
                "subject":     asunto,
                "textContent": mensaje,
            },
            timeout = 10,
        )

        if response.status_code == 201:
            logger.info(f"Email enviado a {destinatario} via Brevo — asunto: {asunto}")
            return True

        logger.error(
            f"Brevo API error {response.status_code} "
            f"al enviar a {destinatario}: {response.text}"
        )
        return False

    except requests.exceptions.Timeout:
        logger.error(f"Timeout (10s) al enviar email a {destinatario}")
        return False
    except Exception as e:
        logger.error(
            f"Error al enviar email a {destinatario} "
            f"— asunto: {asunto} — error: {e}"
        )
        return False


# ------------------------------------------------
# 1. VERIFICACIÓN DE EMAIL (PIN)
# ------------------------------------------------

def enviar_pin_verificacion(user, pin: str) -> bool:
    from configuracion.models import ConfiguracionSistema
    config = ConfiguracionSistema.obtener()

    asunto  = "Verificación de cuenta — ANH"
    mensaje = f"""
Hola {user.nombres},

Gracias por registrarte en el sistema de solicitudes de combustible de la
Agencia Nacional de Hidrocarburos (ANH).

Tu código de verificación es:

    {pin}

Este código expira en {config.tiempo_expiracion_pin_minutos} minutos.

Si no solicitaste este código, ignora este mensaje.

Agencia Nacional de Hidrocarburos
Bolivia
""".strip()

    return _enviar_email(asunto, mensaje, user.email)


# ------------------------------------------------
# 2. RECUPERACIÓN DE CONTRASEÑA (TOKEN UUID)
# ------------------------------------------------

def enviar_token_recuperacion(user, token_uuid: str, por_admin: bool = False) -> bool:
    """
    por_admin=True: reset iniciado por un administrador. La contraseña
    anterior ya quedó inutilizable, así que el cierre del mensaje
    cambia (no se puede decir que "permanecerá sin cambios").
    """
    from configuracion.models import ConfiguracionSistema
    config = ConfiguracionSistema.obtener()

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    enlace = f"{frontend_url}/recuperar-password/confirmar?token={token_uuid}"

    if por_admin:
        intro = (
            "Un administrador restableció la contraseña de tu cuenta\n"
            "en el sistema ANH. Tu contraseña anterior ya no es válida."
        )
        cierre = (
            "Si el enlace vence, puedes pedir uno nuevo desde\n"
            "\"¿Olvidaste tu contraseña?\" en la pantalla de inicio de sesión."
        )
    else:
        intro = (
            "Recibimos una solicitud para restablecer la contraseña de tu cuenta\n"
            "en el sistema ANH."
        )
        cierre = (
            "Si no solicitaste este cambio, ignora este mensaje.\n"
            "Tu contraseña actual permanecerá sin cambios."
        )

    asunto  = "Recuperación de contraseña — ANH"
    mensaje = f"""
Hola {user.nombres},

{intro}

Haz clic en el siguiente enlace para crear una nueva contraseña:

    {enlace}

Este enlace expira en {config.tiempo_expiracion_token_recuperacion_horas} hora(s).

{cierre}

Agencia Nacional de Hidrocarburos
Bolivia
""".strip()

    return _enviar_email(asunto, mensaje, user.email)


# ------------------------------------------------
# 2b. ACTIVACIÓN DE CUENTA CREADA POR ADMIN (TOKEN UUID)
# ------------------------------------------------

def enviar_link_activacion(user, token_uuid: str) -> bool:
    from .services import HORAS_EXPIRACION_ACTIVACION

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    enlace = f"{frontend_url}/activar-cuenta?token={token_uuid}"

    asunto  = "Activa tu cuenta — ANH"
    mensaje = f"""
Hola {user.nombres},

Bienvenido al sistema de solicitudes de combustible de la
Agencia Nacional de Hidrocarburos (ANH). Un administrador creó
tu cuenta con este correo.

Crea tu contraseña en el siguiente enlace para activarla:

    {enlace}

Este enlace expira en {HORAS_EXPIRACION_ACTIVACION} horas. Si vence, puedes pedir
uno nuevo desde la pantalla de inicio de sesión.

Si no esperabas este mensaje, ignóralo.

Agencia Nacional de Hidrocarburos
Bolivia
""".strip()

    return _enviar_email(asunto, mensaje, user.email)


# ------------------------------------------------
# 3. NOTIFICACIÓN — SOLICITUD APROBADA
# ------------------------------------------------

def enviar_notificacion_solicitud_aprobada(solicitud) -> bool:
    user    = solicitud.consumidor.user
    asunto  = "Solicitud aprobada — ANH"
    mensaje = f"""
Hola {user.nombres},

Nos complace informarle que su solicitud de combustible ha sido APROBADA.

Detalles de la aprobación:
  - N° de solicitud : {str(solicitud.id_publico)[:8].upper()}
  - Combustible     : {solicitud.get_tipo_combustible_aprobado_display()}
  - Litros aprobados: {solicitud.litros_aprobados} L
  - Estación        : {solicitud.estacion_servicio.nombre}
  - Dirección       : {solicitud.estacion_servicio.direccion}, {solicitud.estacion_servicio.municipio}
  - Válida hasta    : {formatear_fecha_hora(solicitud.fecha_expiracion)}

Por favor, preséntese en la estación asignada antes de la fecha de vencimiento
con su documento de identidad.

Agencia Nacional de Hidrocarburos
Bolivia
""".strip()

    return _enviar_email(asunto, mensaje, user.email)


# ------------------------------------------------
# 4. NOTIFICACIÓN — SOLICITUD OBSERVADA
# ------------------------------------------------

def enviar_notificacion_solicitud_observada(solicitud) -> bool:
    user    = solicitud.consumidor.user
    asunto  = "Solicitud observada — ANH"
    mensaje = f"""
Hola {user.nombres},

Su solicitud de combustible ha sido OBSERVADA por la ANH
y requiere su atención.

Detalles:
  - N° de solicitud : {str(solicitud.id_publico)[:8].upper()}
  - Observación     : {solicitud.observacion_anh}

Por favor, revise la observación e ingrese al sistema para
corregir o complementar su solicitud.

Agencia Nacional de Hidrocarburos
Bolivia
""".strip()

    return _enviar_email(asunto, mensaje, user.email)


# ------------------------------------------------
# 5. NOTIFICACIÓN — SOLICITUD RECHAZADA
# ------------------------------------------------

def enviar_notificacion_solicitud_rechazada(solicitud) -> bool:
    user    = solicitud.consumidor.user
    asunto  = "Solicitud rechazada — ANH"
    mensaje = f"""
Hola {user.nombres},

Lamentamos informarle que su solicitud de combustible ha sido RECHAZADA.

Detalles:
  - N° de solicitud : {str(solicitud.id_publico)[:8].upper()}
  - Motivo          : {solicitud.observacion_anh}

Si considera que existe un error, puede comunicarse con la
Agencia Nacional de Hidrocarburos para más información.

Agencia Nacional de Hidrocarburos
Bolivia
""".strip()

    return _enviar_email(asunto, mensaje, user.email)