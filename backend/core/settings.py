# core/settings.py

from pathlib import Path
from datetime import timedelta
import environ
import dj_database_url

# ------------------------------------------------
# BASE
# ------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------
# VARIABLES DE ENTORNO
# Lee el archivo .env ubicado en backend/ (en desarrollo).
# En Railway las variables se inyectan directamente,
# por lo que read_env() simplemente no encuentra el
# archivo .env y continúa sin error.
# ------------------------------------------------

env = environ.Env(
    # Define tipos y valores por defecto
    DJANGO_DEBUG=(bool, True),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DB_PORT=(int, 5432),
    EMAIL_PORT=(int, 587),
    EMAIL_USE_TLS=(bool, True),
    CORS_ALLOWED_ORIGINS=(list, ["http://127.0.0.1:5173", "http://localhost:5173"]),
    CSRF_TRUSTED_ORIGINS=(list, ["http://127.0.0.1:5173", "http://localhost:5173"]),
)

environ.Env.read_env(BASE_DIR / ".env")

# ------------------------------------------------
# SEGURIDAD
# ------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG      = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# ------------------------------------------------
# APLICACIONES
# ------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Terceros
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",

    # Tareas periódicas
    

    # Proyecto
    "users.apps.UsersConfig",
    "consumidores.apps.ConsumidoresConfig",
    "estaciones.apps.EstacionesConfig",
    "solicitudes.apps.SolicitudesConfig",
    "configuracion.apps.ConfiguracionConfig",
    "catalogos.apps.CatalogosConfig",
]

# ------------------------------------------------
# MIDDLEWARE
# CorsMiddleware debe ir primero.
# WhiteNoise va justo después de SecurityMiddleware
# para servir los archivos estáticos en producción
# sin necesidad de un servidor web adicional (Nginx).
# ------------------------------------------------

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"

# ------------------------------------------------
# TEMPLATES
# ------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ------------------------------------------------
# BASE DE DATOS
# Si existe DATABASE_URL (Railway la inyecta automáticamente
# al conectar el plugin de PostgreSQL), se usa esa conexión.
# En desarrollo local, usa las variables individuales del .env.
# ------------------------------------------------

if env("DATABASE_URL", default=None):
    DATABASES = {
        "default": dj_database_url.config(
            default=env("DATABASE_URL"),
            conn_max_age=600,
            ssl_require=not DEBUG,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE":   "django.db.backends.postgresql",
            "NAME":     env("DB_NAME"),
            "USER":     env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST":     env("DB_HOST",  default="localhost"),
            "PORT":     env("DB_PORT"),
        }
    }

# ------------------------------------------------
# USUARIO PERSONALIZADO
# ------------------------------------------------

AUTH_USER_MODEL = "users.User"

# ------------------------------------------------
# VALIDACIÓN DE CONTRASEÑAS
# ------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "users.validators.PasswordSeguroValidator"}
]

# ------------------------------------------------
# INTERNACIONALIZACIÓN
# ------------------------------------------------

LANGUAGE_CODE = "es-bo"
TIME_ZONE     = "America/La_Paz"
USE_I18N      = True
USE_TZ        = True

# ------------------------------------------------
# ARCHIVOS ESTÁTICOS Y MEDIA
# STATICFILES_STORAGE con compresión y manifiesto
# para que WhiteNoise sirva los estáticos de forma
# eficiente en producción (Railway).
# ------------------------------------------------

STATIC_URL  = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ------------------------------------------------
# IDs
# ------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------
# DJANGO REST FRAMEWORK
# ------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Lee JWT desde cookie httponly
        # Fallback a header Authorization: Bearer
        "users.authentication.CookieJWTAuthentication",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# ------------------------------------------------
# SIMPLE JWT
# AUTH_COOKIE_SAMESITE en "None" para producción:
# frontend (Vercel) y backend (Railway) están en
# dominios distintos, por lo que las cookies deben
# permitir contexto cross-site. Esto requiere
# AUTH_COOKIE_SECURE=True (ya cubierto por not DEBUG),
# ya que los navegadores exigen Secure junto con
# SameSite=None.
# En desarrollo local (DEBUG=True) se mantiene "Lax"
# porque frontend y backend corren en localhost.
# ------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":    timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME":   timedelta(days=1),
    "ROTATE_REFRESH_TOKENS":    True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES":        ("Bearer",),

    # Nombres de las cookies httponly
    "AUTH_COOKIE":          "access_token",
    "AUTH_COOKIE_REFRESH":  "refresh_token",
    "AUTH_COOKIE_SECURE":   not DEBUG,
    "AUTH_COOKIE_SAMESITE": "None" if not DEBUG else "Lax",
}

# ------------------------------------------------
# CORS
# ------------------------------------------------

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS   = env("CORS_ALLOWED_ORIGINS")
# El frontend (otro origen) lee el nombre del archivo descargado de este
# header en los reportes; sin exponerlo, el navegador lo oculta.
CORS_EXPOSE_HEADERS    = ["Content-Disposition"]
CSRF_TRUSTED_ORIGINS   = env("CSRF_TRUSTED_ORIGINS")

# ------------------------------------------------
# EMAIL
# En desarrollo: muestra emails en consola.
# En producción: configurar SMTP via .env
# ------------------------------------------------

EMAIL_BACKEND       = env("EMAIL_BACKEND",       default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST          = env("EMAIL_HOST",          default="smtp.gmail.com")
EMAIL_PORT          = env.int("EMAIL_PORT",      default=587)
EMAIL_USE_TLS       = env.bool("EMAIL_USE_TLS",  default=True)
EMAIL_USE_SSL       = env.bool("EMAIL_USE_SSL",  default=False)
EMAIL_TIMEOUT       = env.int("EMAIL_TIMEOUT",   default=10)
EMAIL_HOST_USER     = env("EMAIL_HOST_USER",     default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL  = env("DEFAULT_FROM_EMAIL",  default="ANH <noreply@anh.gob.bo>")

# ------------------------------------------------
# BREVO (servicio HTTP de email)
# Usado en producción porque Railway bloquea SMTP
# saliente en el plan Hobby. La API HTTP no se ve
# afectada por esa restricción.
# Si BREVO_API_KEY está vacía, email_service.py hace
# fallback a Django send_mail (consola en desarrollo).
# ------------------------------------------------

BREVO_API_KEY      = env("BREVO_API_KEY",      default="")
BREVO_SENDER_EMAIL = env("BREVO_SENDER_EMAIL", default="alejandro71133089@gmail.com")
BREVO_SENDER_NAME  = env("BREVO_SENDER_NAME",  default="ANH Bolivia")

# ------------------------------------------------
# FRONTEND URL
# Usada para construir enlaces en emails
# (recuperación de contraseña, etc.)
# ------------------------------------------------

FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")

# ------------------------------------------------
# LOGGING
# Handler de consola a nivel INFO acotado a las apps propias
# (no django.* completo, que llenaría los logs con cada request).
# Sin esto, logger.info() no llega a ningún lado: Python solo usa
# su "last resort handler" (WARNING+) cuando no hay logging
# configurado, así que los .info() de la app quedaban invisibles.
# En Railway, la consola es el propio stream de logs del servicio.
# ------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        app: {"handlers": ["console"], "level": "INFO", "propagate": False}
        for app in ["solicitudes", "users", "consumidores", "estaciones"]
    },
}