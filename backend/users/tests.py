# apps/users/tests.py
#
# Cobertura de H1: alta de usuarios por ADMIN/ANH con activación por link
# (sin contraseñas temporales visibles), reset de contraseña por link,
# reenvío de la activación y anti-enumeración en el login.
#
# BREVO_API_KEY se vacía en todas las clases: así _enviar_email usa el
# backend de email de Django, que en tests es locmem (mail.outbox), y
# nunca se llama a la API real aunque el .env local la tenga.

import io
import re
import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken, OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from catalogos.models import Departamento, Municipio, Provincia
from consumidores.models import ConsumidorPerfil
from users.models import TokenVerificacion
from users.services import (
    HORAS_EXPIRACION_ACTIVACION,
    crear_token_verificacion,
    es_activacion_pendiente,
)

User = get_user_model()

PASSWORD_NUEVA = "NuevaClave123!"
RECUP          = TokenVerificacion.TipoToken.RECUPERACION_PASSWORD


# ------------------------------------------------
# HELPERS
# ------------------------------------------------

def _crear_staff(email, tipo):
    user = User.objects.create_user(
        email=email,
        nombres="Staff",
        apellido_paterno="Test",
        tipo_usuario=tipo,
        password="staffpass123",
    )
    user.estado_cuenta    = User.EstadoCuenta.ACTIVO
    user.email_verificado = True
    user.save(update_fields=["estado_cuenta", "email_verificado"])
    return user


def _crear_activo(email, tipo=User.TipoUsuario.CONS, password="clave12345"):
    user = User.objects.create_user(
        email=email,
        nombres="Activo",
        apellido_paterno="Test",
        tipo_usuario=tipo,
        password=password,
    )
    user.estado_cuenta    = User.EstadoCuenta.ACTIVO
    user.email_verificado = True
    user.save(update_fields=["estado_cuenta", "email_verificado"])
    return user


def _crear_pendiente_activacion(email, tipo=User.TipoUsuario.CONS):
    """Mismo estado en que queda una cuenta recién creada por admin."""
    user = User(
        email=email,
        nombres="Pendiente",
        apellido_paterno="Test",
        tipo_usuario=tipo,
    )
    user.set_unusable_password()
    user.save()
    return user


def _token_de_email(mensaje):
    """Extrae el UUID del link de un email."""
    match = re.search(r"token=([0-9a-f-]{36})", mensaje.body)
    assert match, "El email no contiene un link con token"
    return match.group(1)


def _imagen(nombre):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type="image/png")


def _login(client, email, password):
    return client.post(
        reverse("login"), {"email": email, "password": password}, format="json",
    )


# ------------------------------------------------
# ALTA POR ADMIN
# ------------------------------------------------

@override_settings(BREVO_API_KEY="")
class AltaFuncionarioPorAdminTests(TestCase):

    def setUp(self):
        self.admin  = _crear_staff("admin@test.com", User.TipoUsuario.ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _payload(self, **extra):
        data = {
            "email":               "Nuevo.ANH@Test.com",
            "nombres":             "Nuevo",
            "apellido_paterno":    "Funcionario",
            "tipo_usuario":        User.TipoUsuario.ANH,
            "tipo_documento":      "CI",
            "numero_documento":    "1234567",
            "numero_funcionario":  "F-001",
            "cargo":               "Técnico",
            "unidad_departamento": "Fiscalización",
        }
        data.update(extra)
        return data

    def test_alta_anh_queda_pendiente_sin_password_y_envia_link(self):
        response = self.client.post(
            reverse("crear-funcionario"), self._payload(), format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password_temporal", response.data)
        self.assertTrue(response.data["email_enviado"])

        user = User.objects.get(email="nuevo.anh@test.com")
        self.assertEqual(user.estado_cuenta, User.EstadoCuenta.PENDIENTE)
        self.assertFalse(user.email_verificado)
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.requiere_cambio_password)
        self.assertTrue(es_activacion_pendiente(user))

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["nuevo.anh@test.com"])
        self.assertIn("/activar-cuenta?token=", mail.outbox[0].body)

        token = TokenVerificacion.objects.get(token=_token_de_email(mail.outbox[0]))
        self.assertEqual(token.tipo, RECUP)
        self.assertTrue(token.es_valido())
        # Link de 72 h (con margen por el tiempo de ejecución del test)
        horas = (token.fecha_expiracion - timezone.now()) / timedelta(hours=1)
        self.assertAlmostEqual(horas, HORAS_EXPIRACION_ACTIVACION, delta=0.1)

    def test_link_de_activacion_activa_la_cuenta_y_el_login_funciona_sin_pin(self):
        self.client.post(reverse("crear-funcionario"), self._payload(), format="json")
        token = _token_de_email(mail.outbox[0])

        anon     = APIClient()
        response = anon.post(
            reverse("recuperar-password"),
            {"token": token, "password": PASSWORD_NUEVA, "password2": PASSWORD_NUEVA},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        user = User.objects.get(email="nuevo.anh@test.com")
        self.assertEqual(user.estado_cuenta, User.EstadoCuenta.ACTIVO)
        self.assertTrue(user.email_verificado)
        self.assertTrue(user.check_password(PASSWORD_NUEVA))
        self.assertTrue(TokenVerificacion.objects.get(token=token).usado)

        login = _login(anon, "nuevo.anh@test.com", PASSWORD_NUEVA)
        self.assertEqual(login.status_code, 200)
        self.assertNotIn("code", login.data)

    def test_link_no_se_puede_usar_dos_veces(self):
        self.client.post(reverse("crear-funcionario"), self._payload(), format="json")
        token = _token_de_email(mail.outbox[0])
        body  = {"token": token, "password": PASSWORD_NUEVA, "password2": PASSWORD_NUEVA}

        anon = APIClient()
        self.assertEqual(anon.post(reverse("recuperar-password"), body, format="json").status_code, 200)
        self.assertEqual(anon.post(reverse("recuperar-password"), body, format="json").status_code, 400)


@override_settings(BREVO_API_KEY="")
class AltaConsumidorPorAdminTests(TestCase):

    def setUp(self):
        self._media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._media, ignore_errors=True)
        media = override_settings(MEDIA_ROOT=self._media)
        media.enable()
        self.addCleanup(media.disable)

        self.anh    = _crear_staff("anh@test.com", User.TipoUsuario.ANH)
        self.client = APIClient()
        self.client.force_authenticate(user=self.anh)

        dep  = Departamento.objects.create(nombre="La Paz", codigo="LP")
        prov = Provincia.objects.create(departamento=dep, nombre="Murillo", codigo="001")
        mun  = Municipio.objects.create(provincia=prov, nombre="La Paz", codigo="0101")
        self.geo = {"departamento": dep.id, "provincia": prov.id, "municipio": mun.id}

    def _payload(self):
        return {
            "email":            "consumidor@test.com",
            "nombres":          "Juan",
            "apellido_paterno": "Pérez",
            "fecha_nacimiento": "1990-01-01",
            "celular":          "70000000",
            "direccion":        "Calle 1",
            "actividad":        ConsumidorPerfil.ActividadEconomica.AGRICULTURA,
            "tipo_documento":   "CI",
            "numero_documento": "7654321",
            "anverso":          _imagen("anverso.png"),
            "reverso":          _imagen("reverso.png"),
            "foto_sosteniendo": _imagen("foto.png"),
            **self.geo,
        }

    def test_alta_consumidor_queda_pendiente_y_se_activa_por_link(self):
        response = self.client.post(
            reverse("registro-consumidor-por-admin"), self._payload(), format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password_temporal", response.data)
        self.assertTrue(response.data["email_enviado"])

        user = User.objects.get(email="consumidor@test.com")
        self.assertTrue(es_activacion_pendiente(user))
        self.assertFalse(user.email_verificado)

        token = _token_de_email(mail.outbox[0])
        APIClient().post(
            reverse("recuperar-password"),
            {"token": token, "password": PASSWORD_NUEVA, "password2": PASSWORD_NUEVA},
            format="json",
        )

        user.refresh_from_db()
        self.assertEqual(user.estado_cuenta, User.EstadoCuenta.ACTIVO)
        self.assertTrue(user.email_verificado)


# ------------------------------------------------
# LOGIN — ANTI-ENUMERACIÓN
# ------------------------------------------------

@override_settings(BREVO_API_KEY="")
class LoginAntiEnumeracionTests(TestCase):

    def setUp(self):
        self.client = APIClient()

    def test_cuenta_pendiente_responde_igual_que_credenciales_invalidas(self):
        _crear_pendiente_activacion("pendiente@test.com")
        _crear_activo("activo@test.com")

        pendiente   = _login(self.client, "pendiente@test.com", "cualquiera123")
        clave_mala  = _login(self.client, "activo@test.com", "incorrecta123")
        inexistente = _login(self.client, "noexiste@test.com", "cualquiera123")

        self.assertEqual(pendiente.status_code, 400)
        self.assertEqual(pendiente.status_code, clave_mala.status_code)
        self.assertEqual(pendiente.status_code, inexistente.status_code)
        self.assertEqual(pendiente.json(), clave_mala.json())
        self.assertEqual(pendiente.json(), inexistente.json())
        self.assertNotIn("code", pendiente.json())

    def test_pin_pendiente_con_password_correcta_devuelve_code(self):
        # Registro público: tiene contraseña propia, falta el PIN.
        User.objects.create_user(
            email="publico@test.com", nombres="P", apellido_paterno="T",
            tipo_usuario=User.TipoUsuario.CONS, password="clave12345",
        )

        response = _login(self.client, "publico@test.com", "clave12345")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "email_no_verificado")

    def test_pin_pendiente_con_password_incorrecta_no_revela_nada(self):
        User.objects.create_user(
            email="publico@test.com", nombres="P", apellido_paterno="T",
            tipo_usuario=User.TipoUsuario.CONS, password="clave12345",
        )
        _crear_activo("activo@test.com")

        pin_pendiente = _login(self.client, "publico@test.com", "incorrecta123")
        clave_mala    = _login(self.client, "activo@test.com", "incorrecta123")

        self.assertEqual(pin_pendiente.json(), clave_mala.json())


# ------------------------------------------------
# REENVÍO DE LA ACTIVACIÓN
# ------------------------------------------------

@override_settings(BREVO_API_KEY="")
class ReenvioActivacionPublicoTests(TestCase):

    def setUp(self):
        self.client = APIClient()

    def _reenviar(self, email):
        return self.client.post(
            reverse("reenviar-activacion"), {"email": email}, format="json",
        )

    def test_pendiente_recibe_link_nuevo_e_invalida_el_anterior(self):
        user     = _crear_pendiente_activacion("pendiente@test.com")
        anterior = crear_token_verificacion(user, RECUP, horas=HORAS_EXPIRACION_ACTIVACION)

        response = self._reenviar("PENDIENTE@test.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        anterior.refresh_from_db()
        self.assertTrue(anterior.usado)
        nuevo = TokenVerificacion.objects.get(token=_token_de_email(mail.outbox[0]))
        self.assertTrue(nuevo.es_valido())

    def test_respuesta_identica_exista_o_no_el_email(self):
        _crear_pendiente_activacion("pendiente@test.com")
        _crear_activo("activo@test.com")

        pendiente   = self._reenviar("pendiente@test.com")
        activo      = self._reenviar("activo@test.com")
        inexistente = self._reenviar("noexiste@test.com")

        self.assertEqual(pendiente.status_code, activo.status_code)
        self.assertEqual(pendiente.status_code, inexistente.status_code)
        self.assertEqual(pendiente.json(), activo.json())
        self.assertEqual(pendiente.json(), inexistente.json())
        # Solo la cuenta pendiente recibe email
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["pendiente@test.com"])

    def test_link_vencido_sigue_siendo_activacion_y_no_pin(self):
        user  = _crear_pendiente_activacion("pendiente@test.com")
        token = crear_token_verificacion(user, RECUP, horas=HORAS_EXPIRACION_ACTIVACION)
        token.fecha_expiracion = timezone.now() - timedelta(hours=1)
        token.save(update_fields=["fecha_expiracion"])

        # El discriminador no depende del token vigente
        self.assertTrue(es_activacion_pendiente(user))

        # No se le manda PIN (lo dejaría ACTIVO sin contraseña)...
        pin = self.client.post(reverse("reenviar-pin"), {"email": "pendiente@test.com"}, format="json")
        self.assertEqual(pin.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(
            TokenVerificacion.objects.filter(
                user=user, tipo=TokenVerificacion.TipoToken.VERIFICACION_EMAIL,
            ).exists()
        )

        # ...y el reenvío de activación funciona
        self._reenviar("pendiente@test.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/activar-cuenta?token=", mail.outbox[0].body)


@override_settings(BREVO_API_KEY="")
class ReenvioActivacionStaffTests(TestCase):

    def setUp(self):
        self.admin = _crear_staff("admin@test.com", User.TipoUsuario.ADMIN)
        self.anh   = _crear_staff("anh@test.com", User.TipoUsuario.ANH)
        self.client = APIClient()

    def _reenviar(self, como, user):
        self.client.force_authenticate(user=como)
        return self.client.post(
            reverse("usuario-reenviar-activacion", args=[user.id]), format="json",
        )

    def test_admin_reenvia_a_funcionario_e_invalida_tokens_previos(self):
        funcionario = _crear_pendiente_activacion("ess@test.com", User.TipoUsuario.ESS)
        anterior    = crear_token_verificacion(funcionario, RECUP, horas=HORAS_EXPIRACION_ACTIVACION)

        response = self._reenviar(self.admin, funcionario)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["email_enviado"])
        anterior.refresh_from_db()
        self.assertTrue(anterior.usado)
        self.assertEqual(
            TokenVerificacion.objects.filter(user=funcionario, tipo=RECUP, usado=False).count(), 1,
        )

    def test_anh_no_puede_reenviar_a_un_funcionario(self):
        funcionario = _crear_pendiente_activacion("ess@test.com", User.TipoUsuario.ESS)

        response = self._reenviar(self.anh, funcionario)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_anh_puede_reenviar_a_un_consumidor(self):
        consumidor = _crear_pendiente_activacion("cons@test.com")

        response = self._reenviar(self.anh, consumidor)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_cuenta_no_pendiente_devuelve_400(self):
        activo = _crear_activo("activo@test.com")

        response = self._reenviar(self.admin, activo)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)


# ------------------------------------------------
# RESET POR ADMIN / RECUPERACIÓN PÚBLICA
# ------------------------------------------------

@override_settings(BREVO_API_KEY="")
class ResetPorAdminTests(TestCase):

    def setUp(self):
        self.admin  = _crear_staff("admin@test.com", User.TipoUsuario.ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_reset_funcionario_invalida_password_cierra_sesiones_y_envia_link(self):
        funcionario = _crear_activo("ess@test.com", User.TipoUsuario.ESS)
        RefreshToken.for_user(funcionario)  # sesión abierta

        response = self.client.post(
            reverse("funcionario-resetear-password", args=[funcionario.id]), format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password_temporal", response.data)
        self.assertTrue(response.data["email_enviado"])

        funcionario.refresh_from_db()
        self.assertFalse(funcionario.has_usable_password())
        self.assertEqual(funcionario.estado_cuenta, User.EstadoCuenta.ACTIVO)
        outstanding = OutstandingToken.objects.filter(user=funcionario)
        self.assertTrue(outstanding.exists())
        self.assertEqual(
            BlacklistedToken.objects.filter(token__in=outstanding).count(), outstanding.count(),
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/recuperar-password/confirmar?token=", mail.outbox[0].body)
        self.assertIn("Un administrador restableció", mail.outbox[0].body)

    def test_reset_consumidor_por_anh_envia_link(self):
        anh    = _crear_staff("anh@test.com", User.TipoUsuario.ANH)
        user   = _crear_activo("cons@test.com")
        perfil = ConsumidorPerfil.objects.create(user=user, fecha_nacimiento=date(1990, 1, 1))
        self.client.force_authenticate(user=anh)

        response = self.client.post(
            reverse("consumidor-resetear-password", args=[perfil.id]), format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password_temporal", response.data)
        user.refresh_from_db()
        self.assertFalse(user.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)

    def test_reset_de_cuenta_pendiente_devuelve_400_en_ambos_endpoints(self):
        mensaje = "La cuenta está pendiente de activación. Usa reenviar enlace de activación."

        funcionario = _crear_pendiente_activacion("ess@test.com", User.TipoUsuario.ESS)
        response = self.client.post(
            reverse("funcionario-resetear-password", args=[funcionario.id]), format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], mensaje)

        consumidor = _crear_pendiente_activacion("cons@test.com")
        perfil     = ConsumidorPerfil.objects.create(user=consumidor, fecha_nacimiento=date(1990, 1, 1))
        response   = self.client.post(
            reverse("consumidor-resetear-password", args=[perfil.id]), format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], mensaje)

        # Ni email ni tokens nuevos: sigue siendo una activación pendiente
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(TokenVerificacion.objects.filter(user__in=[funcionario, consumidor]).exists())

    def test_recuperacion_publica_funciona_para_activo_con_password_inutilizable(self):
        # Caso "el admin reseteó y el link venció": se pide uno nuevo
        # por la recuperación pública.
        funcionario = _crear_activo("ess@test.com", User.TipoUsuario.ESS)
        self.client.post(reverse("funcionario-resetear-password", args=[funcionario.id]), format="json")
        TokenVerificacion.objects.filter(user=funcionario).update(
            fecha_expiracion=timezone.now() - timedelta(hours=1),
        )

        anon = APIClient()
        anon.post(reverse("solicitar-recuperacion"), {"email": "ess@test.com"}, format="json")
        token = _token_de_email(mail.outbox[-1])

        response = anon.post(
            reverse("recuperar-password"),
            {"token": token, "password": PASSWORD_NUEVA, "password2": PASSWORD_NUEVA},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        funcionario.refresh_from_db()
        self.assertTrue(funcionario.check_password(PASSWORD_NUEVA))
        self.assertEqual(funcionario.estado_cuenta, User.EstadoCuenta.ACTIVO)
        self.assertEqual(_login(anon, "ess@test.com", PASSWORD_NUEVA).status_code, 200)

    def test_cambiar_estado_de_cuenta_pendiente_devuelve_400(self):
        pendiente = _crear_pendiente_activacion("ess@test.com", User.TipoUsuario.ESS)

        response = self.client.post(
            reverse("funcionario-cambiar-estado", args=[pendiente.id]),
            {"estado_cuenta": User.EstadoCuenta.ACTIVO},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado_cuenta, User.EstadoCuenta.PENDIENTE)


@override_settings(BREVO_API_KEY="")
class RecuperacionPublicaTests(TestCase):

    def setUp(self):
        self.client = APIClient()

    def _confirmar(self, token):
        return self.client.post(
            reverse("recuperar-password"),
            {"token": str(token.token), "password": PASSWORD_NUEVA, "password2": PASSWORD_NUEVA},
            format="json",
        )

    def test_recuperacion_de_cuenta_activa_sigue_funcionando(self):
        user = _crear_activo("activo@test.com")

        self.client.post(reverse("solicitar-recuperacion"), {"email": "activo@test.com"}, format="json")
        token = TokenVerificacion.objects.get(token=_token_de_email(mail.outbox[0]))
        response = self._confirmar(token)

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD_NUEVA))
        self.assertEqual(user.estado_cuenta, User.EstadoCuenta.ACTIVO)

    def test_link_nunca_reactiva_una_cuenta_suspendida(self):
        user = _crear_activo("suspendido@test.com")
        user.estado_cuenta = User.EstadoCuenta.SUSPENDIDO
        user.save(update_fields=["estado_cuenta"])
        token = crear_token_verificacion(user, RECUP)

        response = self._confirmar(token)

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.estado_cuenta, User.EstadoCuenta.SUSPENDIDO)
        self.assertTrue(user.check_password(PASSWORD_NUEVA))

    def test_registro_publico_con_pin_no_cambia(self):
        user = User.objects.create_user(
            email="publico@test.com", nombres="P", apellido_paterno="T",
            tipo_usuario=User.TipoUsuario.CONS, password="clave12345",
        )
        self.assertFalse(es_activacion_pendiente(user))

        self.client.post(reverse("reenviar-pin"), {"email": "publico@test.com"}, format="json")
        pin = TokenVerificacion.objects.get(
            user=user, tipo=TokenVerificacion.TipoToken.VERIFICACION_EMAIL, usado=False,
        ).codigo_pin

        response = self.client.post(
            reverse("verificar-email"),
            {"email": "publico@test.com", "codigo_pin": pin},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.estado_cuenta, User.EstadoCuenta.ACTIVO)
        self.assertTrue(user.email_verificado)
        self.assertEqual(_login(self.client, "publico@test.com", "clave12345").status_code, 200)
