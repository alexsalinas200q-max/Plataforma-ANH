# apps/users/urls.py

from django.urls import path

from .views import (
    ReenviarPinView,
    RegistroConsumidorView,
    CrearFuncionarioView,
    FuncionarioListView,
    FuncionarioDetailView,
    FuncionarioCambiarEstadoView,
    FuncionarioResetearPasswordView,
    LoginView,
    RefreshView,
    LogoutView,
    VerificarEmailView,
    SolicitarRecuperacionView,
    RecuperarPasswordView,
    CambiarPasswordView,
    CambiarPasswordObligatorioView,
    MiPerfilView,
    RegistroConsumidorPorAdminView,
    ReenviarActivacionView,
    ReenviarActivacionStaffView,
)

urlpatterns = [

    # ------------------------------------------------
    # REGISTRO
    # ------------------------------------------------
    path("registro/consumidor/",   RegistroConsumidorView.as_view(),  name="registro-consumidor"),
    path("registro/consumidor-por-admin/",  RegistroConsumidorPorAdminView.as_view(),   name="registro-consumidor-por-admin",),
    path("funcionarios/crear/",    CrearFuncionarioView.as_view(),     name="crear-funcionario"),

    # ------------------------------------------------
    # GESTIÓN DE FUNCIONARIOS (ADMIN/ANH)
    # ------------------------------------------------
    path("funcionarios/",          FuncionarioListView.as_view(),      name="funcionarios-list"),
    path("funcionarios/<int:user_id>/",  FuncionarioDetailView.as_view(),    name="funcionario-detail"),
    path("funcionarios/<int:user_id>/cambiar-estado/", FuncionarioCambiarEstadoView.as_view(), name="funcionario-cambiar-estado"),
    path("funcionarios/<int:user_id>/resetear-password/", FuncionarioResetearPasswordView.as_view(), name="funcionario-resetear-password"),

    # ------------------------------------------------
    # ACTIVACIÓN DE CUENTA (ADMIN → cualquier usuario, ANH → consumidores)
    # ------------------------------------------------
    path("usuarios/<int:user_id>/reenviar-activacion/", ReenviarActivacionStaffView.as_view(), name="usuario-reenviar-activacion"),

    # ------------------------------------------------
    # AUTENTICACIÓN
    # ------------------------------------------------
    path("auth/login/",                    LoginView.as_view(),                name="login"),
    path("auth/refresh/",                  RefreshView.as_view(),               name="token-refresh"),
    path("auth/logout/",                   LogoutView.as_view(),                name="logout"),
    path("auth/verificar-email/",          VerificarEmailView.as_view(),        name="verificar-email"),
    path("auth/recuperar-password/",       SolicitarRecuperacionView.as_view(), name="solicitar-recuperacion"),
    path("auth/recuperar-password/confirmar/", RecuperarPasswordView.as_view(), name="recuperar-password"),
    path("auth/reenviar-pin/",             ReenviarPinView.as_view(),           name="reenviar-pin"),
    path("auth/reenviar-activacion/",      ReenviarActivacionView.as_view(),    name="reenviar-activacion"),

    # ------------------------------------------------
    # PERFIL Y CONTRASEÑA
    # ------------------------------------------------
    path("auth/cambiar-password/",         CambiarPasswordView.as_view(),       name="cambiar-password"),
    path("auth/cambiar-password-obligatorio/", CambiarPasswordObligatorioView.as_view(), name="cambiar-password-obligatorio"),
    path("me/",                            MiPerfilView.as_view(),              name="mi-perfil"),
]