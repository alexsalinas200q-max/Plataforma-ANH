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
