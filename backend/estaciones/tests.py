# apps/estaciones/tests.py

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from catalogos.models import Departamento, Municipio, Provincia
from estaciones.models import EstacionServicio

User = get_user_model()


class ListadoEstacionesDireccionTests(TestCase):
    """
    El listado alimenta la tarjeta de cada estación y el modal de
    edición (EstacionesProvincia.tsx arranca el formulario con el
    objeto del listado). Sin `direccion` en el listado, el modal abría
    con Dirección vacía y no se podía guardar sin reescribirla.
    """

    def setUp(self):
        anh = User.objects.create_user(
            email="anh_est@test.com", nombres="ANH", apellido_paterno="Test",
            tipo_usuario=User.TipoUsuario.ANH, password="testpass123",
        )
        anh.estado_cuenta = User.EstadoCuenta.ACTIVO
        anh.save(update_fields=["estado_cuenta"])
        self.client = APIClient()
        self.client.force_authenticate(user=anh)

        dep  = Departamento.objects.create(nombre="La Paz", codigo="LP")
        prov = Provincia.objects.create(departamento=dep, nombre="Murillo", codigo="001")
        mun  = Municipio.objects.create(provincia=prov, nombre="La Paz", codigo="0101")
        self.estacion = EstacionServicio.objects.create(
            nombre="Estación Centro", codigo="EST-001",
            direccion="Av. 6 de Agosto 123", municipio=mun,
        )

    def _item_del_listado(self):
        response = self.client.get(reverse("estacion-list"))
        self.assertEqual(response.status_code, 200)
        resultados = response.data.get("results", response.data)
        return next(e for e in resultados if e["id"] == self.estacion.id)

    def test_listado_incluye_direccion(self):
        self.assertEqual(self._item_del_listado()["direccion"], "Av. 6 de Agosto 123")

    def test_editar_con_datos_del_listado_guarda_sin_reescribir_direccion(self):
        item = self._item_del_listado()

        # Mismo payload que arma el modal: solo se cambia el nombre.
        response = self.client.put(
            reverse("estacion-detail", args=[self.estacion.id]),
            {
                "nombre":    "Estación Centro Renovada",
                "codigo":    item["codigo"],
                "direccion": item["direccion"],
                "municipio": item["municipio"],
                "estado":    item["estado"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.estacion.refresh_from_db()
        self.assertEqual(self.estacion.nombre, "Estación Centro Renovada")
        self.assertEqual(self.estacion.direccion, "Av. 6 de Agosto 123")
