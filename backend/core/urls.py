# core/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


from solicitudes.views_reportes import ReporteConsumidoresView
from solicitudes.views_dashboard import DashboardANHView
from solicitudes.views_estadisticas import EstadisticasSolicitudesView, ReporteSolicitudesView

urlpatterns = [

    # ------------------------------------------------
    # ADMIN
    # ------------------------------------------------

    path("admin/", admin.site.urls),

    # ------------------------------------------------
    # USERS — autenticación, registro, perfil
    #
    # Rutas generadas:
    #   POST   api/users/registro/consumidor/
    #   POST   api/users/funcionarios/crear/
    #   POST   api/users/auth/login/
    #   POST   api/users/auth/refresh/
    #   POST   api/users/auth/logout/
    #   POST   api/users/auth/verificar-email/
    #   POST   api/users/auth/recuperar-password/
    #   POST   api/users/auth/recuperar-password/confirmar/   (también activa cuentas PENDIENTE)
    #   POST   api/users/auth/reenviar-activacion/
    #   POST   api/users/usuarios/{id}/reenviar-activacion/
    #   POST   api/users/auth/cambiar-password/
    #   GET    api/users/me/
    # ------------------------------------------------

    path("api/catalogos/", include("catalogos.urls")),
    path("api/users/", include("users.urls")),

    # ------------------------------------------------
    # CONSUMIDORES — perfil y documentos
    #
    # Rutas generadas:
    #   GET    api/consumidores/me/
    #   PATCH  api/consumidores/me/
    #   GET    api/consumidores/me/documentos/
    #   POST   api/consumidores/me/documentos/
    #   GET    api/consumidores/
    #   GET    api/consumidores/{id}/
    #   POST   api/consumidores/{id}/verificar/
    # ------------------------------------------------

    path("api/", include("consumidores.urls")),

    # ------------------------------------------------
    # ESTACIONES — gestión de estaciones de servicio
    #
    # Rutas generadas:
    #   GET    api/estaciones/
    #   POST   api/estaciones/
    #   GET    api/estaciones/{id}/
    #   PUT    api/estaciones/{id}/
    #   PATCH  api/estaciones/{id}/
    #   POST   api/estaciones/{id}/cambiar-estado/
    # ------------------------------------------------

    path("api/", include("estaciones.urls")),

    # ------------------------------------------------
    # SOLICITUDES — gestión de solicitudes de combustible
    #
    # Rutas generadas:
    #   GET    api/solicitudes/
    #   POST   api/solicitudes/
    #   GET    api/solicitudes/{id_publico}/
    #   POST   api/solicitudes/{id_publico}/aprobar/
    #   POST   api/solicitudes/{id_publico}/observar/
    #   POST   api/solicitudes/{id_publico}/rechazar/
    #   POST   api/solicitudes/{id_publico}/despachar/
    #   GET    api/solicitudes/mi-disponible/
    #   GET    api/solicitudes/cupo-consumidor/{consumidor_id}/
    # ------------------------------------------------

    path("api/", include("solicitudes.urls")),
    path("api/dashboard/", DashboardANHView.as_view(), name="dashboard-anh"),
    path(
        "api/reportes/consumidores/",
        ReporteConsumidoresView.as_view(),
        name="reporte-consumidores"
    ),
    path("api/estadisticas/solicitudes/", EstadisticasSolicitudesView.as_view()),
    path("api/reportes/solicitudes/", ReporteSolicitudesView.as_view()),

]

# ------------------------------------------------
# ARCHIVOS MEDIA Y STATIC EN DESARROLLO
# ------------------------------------------------

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATIC_ROOT
    )