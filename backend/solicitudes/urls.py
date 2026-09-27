# apps/solicitudes/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import SolicitudViewSet, MiDisponibleView, CupoConsumidorView


router = DefaultRouter()

router.register(
    r"solicitudes",
    SolicitudViewSet,
    basename="solicitud"
)


urlpatterns = [

    # ------------------------------------------------
    # CUPO MENSUAL
    # Van antes del router: si no, el router intentaría matchear
    # "mi-disponible" como si fuera un {id_publico} de la ruta de
    # detalle de SolicitudViewSet.
    # ------------------------------------------------

    path(
        "solicitudes/mi-disponible/",
        MiDisponibleView.as_view(),
        name="mi-disponible"
    ),
    path(
        "solicitudes/cupo-consumidor/<int:consumidor_id>/",
        CupoConsumidorView.as_view(),
        name="cupo-consumidor"
    ),

    path("", include(router.urls)),
]