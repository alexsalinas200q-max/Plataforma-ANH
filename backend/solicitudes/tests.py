# apps/solicitudes/tests.py
#
# Cobertura de las dos reglas duras agregadas por validar_cupo.py:
# cupo mensual de 120L y unicidad de solicitud activa. No se testea
# acá el resto del ciclo de vida de Solicitud (aprobar/despachar/etc.),
# que no tiene suite propia todavía.

from datetime import date, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from catalogos.models import Departamento, Municipio, Provincia
from consumidores.models import ConsumidorPerfil
from estaciones.models import EstacionServicio
from solicitudes.models import Solicitud
from solicitudes.services.aprobar_solicitud import aprobar_solicitud
from solicitudes.services.validar_cupo import (
    calcular_cupo_mensual,
    obtener_solicitud_activa,
    verificar_puede_aprobar,
    verificar_puede_crear_solicitud,
)

User = get_user_model()


def _crear_consumidor(email, estado_identidad=None):
    user = User.objects.create_user(
        email=email,
        nombres="Test",
        apellido_paterno="Consumidor",
        tipo_usuario=User.TipoUsuario.CONS,
        password="testpass123",
    )
    perfil = ConsumidorPerfil.objects.create(
        user=user,
        fecha_nacimiento=date(1990, 1, 1),
    )
    if estado_identidad:
        perfil.estado_identidad = estado_identidad
        perfil.save(update_fields=["estado_identidad"])
    return perfil


def _crear_solicitud(
    consumidor,
    estado,
    litros_solicitados=50,
    litros_aprobados=None,
    fecha_aprobacion=None,
):
    # creado_por y declaracion_jurada_confirmada no son necesarios para
    # los tests que solo leen el estado/acumulado vía queryset, pero sí
    # los exige Solicitud.full_clean() — se setean siempre para que los
    # tests de integración (que sí llaman aprobar_solicitud(), y por lo
    # tanto full_clean()) no fallen por un fixture incompleto.
    return Solicitud.objects.create(
        consumidor=consumidor,
        creado_por=consumidor.user,
        tipo_combustible=Solicitud.TipoCombustible.GASOLINA,
        litros_solicitados=litros_solicitados,
        estado=estado,
        litros_aprobados=litros_aprobados,
        fecha_aprobacion=fecha_aprobacion,
        declaracion_jurada_confirmada=True,
        fecha_declaracion_jurada=timezone.now(),
    )


def _crear_cadena_geografica():
    departamento = Departamento.objects.create(nombre="La Paz", codigo="LP")
    provincia = Provincia.objects.create(
        departamento=departamento, nombre="Murillo", codigo="001",
    )
    municipio = Municipio.objects.create(
        provincia=provincia, nombre="La Paz", codigo="0101",
    )
    return departamento, provincia, municipio


def _crear_estacion(codigo="EST-TEST-1", municipio=None):
    # municipio es NOT NULL a nivel de BD (migración 0005_finalizar_
    # municipio_fk), aunque el campo del modelo todavía declare
    # null=True — se arma la cadena completa del catálogo si no
    # se pasa una ya existente.
    if municipio is None:
        _, _, municipio = _crear_cadena_geografica()
    return EstacionServicio.objects.create(
        nombre="Estación de prueba",
        codigo=codigo,
        direccion="Calle Falsa 123",
        municipio=municipio,
    )


class CalcularCupoMensualTests(TestCase):

    def setUp(self):
        self.consumidor = _crear_consumidor("cupo1@test.com")

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_solicitud_aprobada_mes_anterior_no_cuenta_para_mes_siguiente(self, mock_localdate):
        # "Hoy" es 1 de octubre — la solicitud del 30/sept no debe
        # arrastrarse al cupo de octubre (corte de mes calendario).
        mock_localdate.return_value = date(2026, 10, 1)

        fecha_sept = timezone.make_aware(datetime(2026, 9, 30, 10, 0))
        _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.DESPACHADA,
            litros_aprobados=100, fecha_aprobacion=fecha_sept,
        )

        cupo = calcular_cupo_mensual(self.consumidor)
        self.assertEqual(cupo["usado"], 0)
        self.assertEqual(cupo["disponible"], 120)
        self.assertEqual(cupo["mes"], "2026-10")

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_rechazada_no_cuenta_al_acumulado(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        fecha = timezone.make_aware(datetime(2026, 9, 10, 10, 0))
        _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.RECHAZADA,
            litros_aprobados=100, fecha_aprobacion=fecha,
        )
        cupo = calcular_cupo_mensual(self.consumidor)
        self.assertEqual(cupo["usado"], 0)

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_vencida_no_cuenta_al_acumulado(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        fecha = timezone.make_aware(datetime(2026, 9, 10, 10, 0))
        _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.EXPIRADA,
            litros_aprobados=100, fecha_aprobacion=fecha,
        )
        cupo = calcular_cupo_mensual(self.consumidor)
        self.assertEqual(cupo["usado"], 0)

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_aprobada_y_despachada_del_mismo_mes_se_suman(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        fecha1 = timezone.make_aware(datetime(2026, 9, 5, 10, 0))
        fecha2 = timezone.make_aware(datetime(2026, 9, 10, 10, 0))
        _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.DESPACHADA,
            litros_aprobados=60, fecha_aprobacion=fecha1,
        )
        _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.DESPACHADA,
            litros_aprobados=40, fecha_aprobacion=fecha2,
        )
        cupo = calcular_cupo_mensual(self.consumidor)
        self.assertEqual(cupo["usado"], 100)
        self.assertEqual(cupo["disponible"], 20)


class SolicitudActivaTests(TestCase):

    def setUp(self):
        self.consumidor = _crear_consumidor("activa1@test.com")

    def test_sin_solicitudes_no_hay_activa(self):
        self.assertIsNone(obtener_solicitud_activa(self.consumidor))

    def test_pendiente_es_activa(self):
        s = _crear_solicitud(self.consumidor, Solicitud.EstadoSolicitud.PENDIENTE)
        self.assertEqual(obtener_solicitud_activa(self.consumidor), s)

    def test_despachada_no_es_activa(self):
        _crear_solicitud(self.consumidor, Solicitud.EstadoSolicitud.DESPACHADA)
        self.assertIsNone(obtener_solicitud_activa(self.consumidor))

    def test_constraint_bd_bloquea_segunda_solicitud_activa(self):
        # Garantía dura contra condiciones de carrera — sigue vigente,
        # sin cambios, tal como estaba antes de este fix.
        _crear_solicitud(self.consumidor, Solicitud.EstadoSolicitud.PENDIENTE)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _crear_solicitud(self.consumidor, Solicitud.EstadoSolicitud.OBSERVADA)

    def test_alerta_repetitividad_en_revision_no_bloquea_creacion(self):
        # EN_REVISION es un valor de ConsumidorPerfil.alerta_repetitividad,
        # no de Solicitud.estado — no debe afectar esta regla. Solo
        # BLOQUEADO bloquea (esta_bloqueado()), comportamiento sin cambios.
        self.consumidor.alerta_repetitividad = ConsumidorPerfil.EstadoAlerta.EN_REVISION
        self.consumidor.save(update_fields=["alerta_repetitividad"])

        self.assertFalse(self.consumidor.esta_bloqueado())
        puede, _ = verificar_puede_crear_solicitud(self.consumidor, 50)
        self.assertTrue(puede)


class VerificarPuedeCrearSolicitudTests(TestCase):

    def setUp(self):
        self.consumidor = _crear_consumidor("crear1@test.com")

    def test_bloquea_si_tiene_solicitud_activa(self):
        _crear_solicitud(self.consumidor, Solicitud.EstadoSolicitud.PENDIENTE)
        puede, mensaje = verificar_puede_crear_solicitud(self.consumidor, 50)
        self.assertFalse(puede)
        self.assertIn("solicitud activa", mensaje)
        self.assertIn("Ya tienes", mensaje)

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_bloquea_si_excede_cupo_sin_historial(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        puede, mensaje = verificar_puede_crear_solicitud(self.consumidor, 150)
        self.assertFalse(puede)
        self.assertIn("cupo mensual", mensaje)
        self.assertIn("Ya tienes", mensaje)

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_bloquea_si_100l_aprobados_y_pide_50(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        fecha = timezone.make_aware(datetime(2026, 9, 5, 10, 0))
        _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.DESPACHADA,
            litros_aprobados=100, fecha_aprobacion=fecha,
        )
        puede, mensaje = verificar_puede_crear_solicitud(self.consumidor, 50)
        self.assertFalse(puede)
        self.assertIn("100", mensaje)
        self.assertIn("20", mensaje)

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_permite_dentro_de_cupo_y_sin_activa(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        puede, mensaje = verificar_puede_crear_solicitud(self.consumidor, 100)
        self.assertTrue(puede)
        self.assertEqual(mensaje, "")


class VerificarPuedeAprobarTests(TestCase):

    def setUp(self):
        self.consumidor = _crear_consumidor("aprobar1@test.com")

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_bloquea_si_aprobar_excederia_cupo(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        fecha = timezone.make_aware(datetime(2026, 9, 5, 10, 0))
        _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.DESPACHADA,
            litros_aprobados=100, fecha_aprobacion=fecha,
        )
        pendiente = _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.PENDIENTE,
            litros_solicitados=50,
        )
        puede, mensaje = verificar_puede_aprobar(pendiente, 50)
        self.assertFalse(puede)
        self.assertIn("cupo mensual", mensaje)

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_permite_si_aprobacion_entra_en_cupo(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        pendiente = _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.PENDIENTE,
            litros_solicitados=50,
        )
        puede, mensaje = verificar_puede_aprobar(pendiente, 50)
        self.assertTrue(puede)


class AprobarSolicitudCupoIntegrationTests(TestCase):
    """
    Integración end-to-end del punto 5 de las decisiones aprobadas:
    ANH aprueba una solicitud que excedería el cupo → debe fallar con
    un ValidationError amigable, sin llegar a cambiar el estado.
    """

    def setUp(self):
        self.consumidor = _crear_consumidor(
            "aprobar_full@test.com",
            estado_identidad=ConsumidorPerfil.EstadoIdentidad.VERIFICADO,
        )
        self.anh_user = User.objects.create_user(
            email="anh_full@test.com",
            nombres="ANH",
            apellido_paterno="Test",
            tipo_usuario=User.TipoUsuario.ANH,
            password="testpass123",
        )
        self.estacion = _crear_estacion()

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_anh_aprueba_solicitud_que_excederia_cupo(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        fecha = timezone.make_aware(datetime(2026, 9, 5, 10, 0))
        _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.DESPACHADA,
            litros_aprobados=100, fecha_aprobacion=fecha,
        )
        pendiente = _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.PENDIENTE,
            litros_solicitados=50,
        )

        with self.assertRaises(DjangoValidationError) as ctx:
            aprobar_solicitud(
                solicitud_id=pendiente.id,
                usuario_aprobador=self.anh_user,
                estacion_servicio=self.estacion,
                litros_aprobados=50,
                tipo_combustible_aprobado=Solicitud.TipoCombustible.GASOLINA,
            )
        self.assertIn("cupo mensual", str(ctx.exception))

        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_anh_aprueba_solicitud_dentro_de_cupo(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        pendiente = _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.PENDIENTE,
            litros_solicitados=50,
        )

        resultado = aprobar_solicitud(
            solicitud_id=pendiente.id,
            usuario_aprobador=self.anh_user,
            estacion_servicio=self.estacion,
            litros_aprobados=50,
            tipo_combustible_aprobado=Solicitud.TipoCombustible.GASOLINA,
        )
        self.assertEqual(resultado.estado, Solicitud.EstadoSolicitud.APROBADA)


class SolicitudCreateAPITests(TestCase):
    """
    Integración vía API real de SolicitudCreateSerializer.validate() —
    a diferencia de los tests anteriores (que llaman las funciones de
    validar_cupo.py directo), acá se ejercita self.context["request"]
    tal como lo arma DRF en un request HTTP real, para no dar por
    buena esa integración solo por inspección de código.
    """

    def setUp(self):
        self.consumidor = _crear_consumidor("api_create@test.com")
        self.consumidor.user.estado_cuenta = self.consumidor.user.EstadoCuenta.ACTIVO
        self.consumidor.user.save(update_fields=["estado_cuenta"])

        _, _, municipio = _crear_cadena_geografica()
        self.estacion = _crear_estacion(municipio=municipio)
        self.municipio = municipio

        self.client = APIClient()
        self.client.force_authenticate(user=self.consumidor.user)

    def _payload(self, litros=50):
        return {
            "tipo_combustible": Solicitud.TipoCombustible.GASOLINA,
            "litros_solicitados": litros,
            "declaracion_jurada_confirmada": True,
            "departamento": self.municipio.provincia.departamento_id,
            "provincia": self.municipio.provincia_id,
            "municipio": self.municipio.id,
            "estacion_servicio": self.estacion.id,
        }

    def test_bloquea_creacion_si_ya_tiene_activa(self):
        _crear_solicitud(self.consumidor, Solicitud.EstadoSolicitud.PENDIENTE)

        response = self.client.post(
            reverse("solicitud-list"), self._payload(), format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("solicitud activa", str(response.data))

    @patch("solicitudes.services.validar_cupo.timezone.localdate")
    def test_bloquea_creacion_si_excede_cupo(self, mock_localdate):
        mock_localdate.return_value = date(2026, 9, 15)
        fecha = timezone.make_aware(datetime(2026, 9, 5, 10, 0))
        _crear_solicitud(
            self.consumidor, Solicitud.EstadoSolicitud.DESPACHADA,
            litros_aprobados=100, fecha_aprobacion=fecha,
        )

        response = self.client.post(
            reverse("solicitud-list"), self._payload(litros=50), format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cupo mensual", str(response.data))

    def test_permite_creacion_dentro_de_cupo_y_sin_activa(self):
        response = self.client.post(
            reverse("solicitud-list"), self._payload(litros=50), format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)


# ------------------------------------------------
# LOTE A — FECHAS EN HORA LOCAL (America/La_Paz, UTC-4)
# ------------------------------------------------

def _utc(*args):
    from datetime import timezone as dt_timezone
    return datetime(*args, tzinfo=dt_timezone.utc)


def _crear_con_fecha(consumidor, fecha_creacion):
    # CANCELADA: no choca con la constraint de "una activa por consumidor".
    # fecha_creacion es auto_now_add, así que se pisa con update().
    s = _crear_solicitud(consumidor, Solicitud.EstadoSolicitud.CANCELADA)
    Solicitud.objects.filter(pk=s.pk).update(fecha_creacion=fecha_creacion)
    return s


class DashboardHoraLocalTests(TestCase):

    def setUp(self):
        self.anh = User.objects.create_user(
            email="anh_dash@test.com", nombres="ANH", apellido_paterno="Dash",
            tipo_usuario=User.TipoUsuario.ANH, password="testpass123",
        )
        self.anh.estado_cuenta = User.EstadoCuenta.ACTIVO
        self.anh.save(update_fields=["estado_cuenta"])
        self.client = APIClient()
        self.client.force_authenticate(user=self.anh)
        self.consumidor = _crear_consumidor("cons_dash@test.com")

    def _dashboard(self, ahora_utc):
        with patch("django.utils.timezone.now", return_value=ahora_utc):
            response = self.client.get(reverse("dashboard-anh"))
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_solicitud_de_las_21_hora_local_cuenta_como_hoy(self):
        # "Ahora": 21:30 del 10/09 en La Paz = 01:30 UTC del 11/09
        _crear_con_fecha(self.consumidor, _utc(2026, 9, 11, 1, 0))   # 21:00 local del 10
        _crear_con_fecha(self.consumidor, _utc(2026, 9, 10, 23, 0))  # 19:00 local del 10
        _crear_con_fecha(self.consumidor, _utc(2026, 9, 10, 1, 0))   # 21:00 local del 09

        data = self._dashboard(_utc(2026, 9, 11, 1, 30))

        # Con la medianoche UTC, "hoy" arrancaba a las 20:00 del 10 y
        # la de las 19:00 quedaba afuera.
        self.assertEqual(data["solicitudes"]["hoy"]["nuevas"], 2)

        tendencia = data["tendencia_7_dias"]
        self.assertEqual(tendencia[-1]["fecha"], "10/09")
        self.assertEqual(tendencia[-1]["solicitudes"], 2)
        self.assertEqual(tendencia[-2]["fecha"], "09/09")
        self.assertEqual(tendencia[-2]["solicitudes"], 1)
        self.assertEqual(data["generado_en"], "10/09/2026 21:30")

    def test_solicitud_de_anoche_no_cuenta_como_hoy_a_la_manana(self):
        _crear_con_fecha(self.consumidor, _utc(2026, 9, 11, 1, 0))   # 21:00 local del 10

        # 10:00 del 11/09 en La Paz = 14:00 UTC del 11/09
        data = self._dashboard(_utc(2026, 9, 11, 14, 0))

        self.assertEqual(data["solicitudes"]["hoy"]["nuevas"], 0)
        self.assertEqual(data["tendencia_7_dias"][-2]["fecha"], "10/09")
        self.assertEqual(data["tendencia_7_dias"][-2]["solicitudes"], 1)


class EstadisticasMesEspanolTests(TestCase):

    def test_evolucion_mensual_con_meses_en_espanol_y_hora_local(self):
        anh = User.objects.create_user(
            email="anh_est@test.com", nombres="ANH", apellido_paterno="Est",
            tipo_usuario=User.TipoUsuario.ANH, password="testpass123",
        )
        anh.estado_cuenta = User.EstadoCuenta.ACTIVO
        anh.save(update_fields=["estado_cuenta"])
        client = APIClient()
        client.force_authenticate(user=anh)

        consumidor = _crear_consumidor("cons_est@test.com")
        # 02:00 UTC del 1° de febrero = 22:00 local del 31 de enero
        _crear_con_fecha(consumidor, _utc(2026, 2, 1, 2, 0))

        with patch("django.utils.timezone.now", return_value=_utc(2026, 9, 10, 15, 0)):
            response = client.get("/api/estadisticas/solicitudes/")

        self.assertEqual(response.status_code, 200)
        meses = [m["mes"] for m in response.data["por_mes"]]
        self.assertEqual(meses, ["Ene 2026"])


class DeclaracionJuradaFechaTests(TestCase):

    def test_lugar_y_fecha_con_mes_en_espanol(self):
        from reportlab import rl_config
        from solicitudes.services.generar_declaracion_jurada import generar_declaracion_jurada

        consumidor = _crear_consumidor("cons_dj@test.com")
        solicitud  = _crear_solicitud(consumidor, Solicitud.EstadoSolicitud.PENDIENTE)

        # 02:00 UTC del 28/09 = 22:00 local del 27/09. Sin compresión de
        # página el texto queda legible en los bytes del PDF.
        ahora = timezone.localtime(_utc(2026, 9, 28, 2, 0))
        with patch("solicitudes.services.generar_declaracion_jurada.ahora_local", return_value=ahora), \
             patch.object(rl_config, "pageCompression", 0):
            pdf = generar_declaracion_jurada(solicitud)

        self.assertIn(b"27 de septiembre de 2026", pdf)
        self.assertNotIn(b"September", pdf)


class EmailAprobacionHoraLocalTests(TestCase):

    def test_valida_hasta_en_hora_local(self):
        from django.core import mail
        from django.test import override_settings
        from users.email_service import enviar_notificacion_solicitud_aprobada

        consumidor = _crear_consumidor("cons_mail@test.com")
        solicitud  = _crear_solicitud(consumidor, Solicitud.EstadoSolicitud.APROBADA, litros_aprobados=50)
        solicitud.estacion_servicio         = _crear_estacion()
        solicitud.tipo_combustible_aprobado = Solicitud.TipoCombustible.GASOLINA
        solicitud.fecha_expiracion          = _utc(2026, 9, 11, 1, 45)  # 21:45 local del 10

        with override_settings(BREVO_API_KEY=""):
            enviar_notificacion_solicitud_aprobada(solicitud)

        self.assertIn("Válida hasta    : 10/09/2026 21:45", mail.outbox[0].body)


# ------------------------------------------------
# LOTE B — MOTIVO VISIBLE EN EL HISTORIAL DEL CONSUMIDOR (H2)
# ------------------------------------------------

class ListadoExponeMotivoTests(TestCase):

    def test_listado_del_consumidor_incluye_observacion_anh(self):
        consumidor = _crear_consumidor("cons_motivo@test.com")
        consumidor.user.estado_cuenta = User.EstadoCuenta.ACTIVO
        consumidor.user.save(update_fields=["estado_cuenta"])

        s = _crear_solicitud(consumidor, Solicitud.EstadoSolicitud.RECHAZADA)
        Solicitud.objects.filter(pk=s.pk).update(
            observacion_anh="Documento ilegible.",
        )

        client = APIClient()
        client.force_authenticate(user=consumidor.user)
        response = client.get(reverse("solicitud-list"))

        self.assertEqual(response.status_code, 200)
        fila = response.data["results"][0]
        self.assertEqual(fila["estado"], "RECHAZADA")
        self.assertEqual(fila["observacion_anh"], "Documento ilegible.")


class RechazoAutomaticoMotivoTests(TestCase):

    def test_rechazo_por_vencimiento_escribe_motivo_fijo(self):
        from django.test import override_settings
        from solicitudes.services.expirar_solicitudes import rechazar_observadas_vencidas

        consumidor = _crear_consumidor("cons_auto@test.com")
        s = _crear_solicitud(consumidor, Solicitud.EstadoSolicitud.OBSERVADA)
        Solicitud.objects.filter(pk=s.pk).update(
            observacion_anh="Adjunta una foto legible del CI.",
            fecha_limite_respuesta=timezone.now() - timezone.timedelta(hours=1),
        )

        with override_settings(BREVO_API_KEY=""):
            self.assertEqual(rechazar_observadas_vencidas(), 1)

        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.RECHAZADA)
        self.assertEqual(
            s.observacion_anh,
            "Rechazada automáticamente: no se respondió la observación dentro del plazo.",
        )


# ------------------------------------------------
# LOTE D — HISTORIAL POR CONSUMIDOR (ANH/ADMIN)
# ------------------------------------------------

class HistorialPorConsumidorTests(TestCase):

    def test_filtro_por_consumidor_con_estacion(self):
        anh = User.objects.create_user(
            email="anh_hist@test.com", nombres="ANH", apellido_paterno="Hist",
            tipo_usuario=User.TipoUsuario.ANH, password="testpass123",
        )
        anh.estado_cuenta = User.EstadoCuenta.ACTIVO
        anh.save(update_fields=["estado_cuenta"])
        client = APIClient()
        client.force_authenticate(user=anh)

        consumidor = _crear_consumidor("cons_hist@test.com")
        otro       = _crear_consumidor("otro_hist@test.com")
        estacion   = _crear_estacion()

        propia = _crear_solicitud(consumidor, Solicitud.EstadoSolicitud.DESPACHADA)
        Solicitud.objects.filter(pk=propia.pk).update(estacion_servicio=estacion)
        _crear_solicitud(consumidor, Solicitud.EstadoSolicitud.CANCELADA)
        _crear_solicitud(otro, Solicitud.EstadoSolicitud.CANCELADA)

        response = client.get(reverse("solicitud-list"), {"consumidor": consumidor.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        por_id = {r["id_publico"]: r for r in response.data["results"]}
        self.assertEqual(por_id[str(propia.id_publico)]["estacion_nombre"], "Estación de prueba")
        sin_estacion = next(r for r in response.data["results"] if r["id_publico"] != str(propia.id_publico))
        self.assertEqual(sin_estacion["estacion_nombre"], "—")
