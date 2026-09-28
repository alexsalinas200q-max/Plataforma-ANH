# core/tests.py
#
# Helper de fechas (core/fechas.py): conversión a hora local
# (America/La_Paz, UTC-4) y nombres de meses en español.

from datetime import date, datetime, timezone as dt_timezone

from django.test import SimpleTestCase

from core.fechas import (
    formatear_dia_mes,
    formatear_fecha,
    formatear_fecha_hora,
    formatear_fecha_larga,
    formatear_mes_anio,
    inicio_dia_local,
)


def _utc(*args):
    return datetime(*args, tzinfo=dt_timezone.utc)


class FormatoHoraLocalTests(SimpleTestCase):

    def test_utc_de_madrugada_se_formatea_como_la_noche_anterior_local(self):
        # 01:45 UTC del 11 = 21:45 del 10 en La Paz
        valor = _utc(2026, 9, 11, 1, 45)

        self.assertEqual(formatear_fecha_hora(valor), "10/09/2026 21:45")
        self.assertEqual(formatear_fecha(valor), "10/09/2026")
        self.assertEqual(formatear_dia_mes(valor), "10/09")

    def test_date_y_none(self):
        self.assertEqual(formatear_fecha(date(1990, 1, 5)), "05/01/1990")
        self.assertEqual(formatear_fecha(None), "—")
        self.assertEqual(formatear_fecha_hora(None), "—")

    def test_inicio_dia_local_es_la_medianoche_de_la_paz(self):
        inicio = inicio_dia_local(date(2026, 9, 10))
        self.assertEqual(inicio, _utc(2026, 9, 10, 4, 0))


class MesesEnEspanolTests(SimpleTestCase):

    def test_fecha_larga(self):
        self.assertEqual(
            formatear_fecha_larga(date(2026, 9, 27)), "27 de septiembre de 2026",
        )
        # 01:00 UTC del 1° de enero = 31 de diciembre local
        self.assertEqual(
            formatear_fecha_larga(_utc(2026, 1, 1, 1, 0)), "31 de diciembre de 2025",
        )

    def test_mes_anio(self):
        self.assertEqual(formatear_mes_anio(date(2026, 1, 15)), "Ene 2026")
        self.assertEqual(formatear_mes_anio(date(2026, 8, 1)), "Ago 2026")
        self.assertEqual(formatear_mes_anio(date(2026, 12, 31)), "Dic 2026")
