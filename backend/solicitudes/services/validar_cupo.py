# apps/solicitudes/services/validar_cupo.py
#
# Reglas duras de negocio (normativa boliviana, sustancias controladas):
#   1. Cupo de 120 L por consumidor por mes calendario (America/La_Paz).
#   2. Máximo 1 solicitud activa simultánea por consumidor.
#
# Reemplaza, para estas dos reglas puntuales, lo que antes solo se
# detectaba de forma reactiva en verificar_repetitividad.py (ver
# comentario de deprecación en ese archivo).

from datetime import datetime, time

from django.db.models import Sum
from django.utils import timezone

CUPO_MENSUAL_LITROS = 120

# Mismos estados que unique_solicitud_activa_por_consumidor en
# Solicitud.Meta.constraints (models.py). Se repite acá como
# constante en vez de importarla del modelo porque el condition de
# un UniqueConstraint no es introspectable como lista de Python.
ESTADOS_ACTIVOS = ["PENDIENTE", "OBSERVADA", "APROBADA"]

# Estados que sí acumulan cupo mensual: aprobado y ya materializado
# en un despacho. RECHAZADA y EXPIRADA nunca llegaron a consumir
# combustible real y no deben contar.
ESTADOS_QUE_CONSUMEN_CUPO = ["APROBADA", "DESPACHADA"]


def _primer_dia_mes_actual_aware():
    """
    00:00 del día 1 del mes actual, hora America/La Paz, como
    datetime aware. Usa timezone.localdate() (no timezone.now().date())
    para que el corte de mes respete la zona horaria configurada en
    settings.TIME_ZONE en vez de UTC.
    """
    primer_dia = timezone.localdate().replace(day=1)
    return timezone.make_aware(datetime.combine(primer_dia, time.min))


def calcular_cupo_mensual(consumidor) -> dict:
    """
    Litros acumulados por el consumidor en el mes calendario actual,
    sumando litros_aprobados de solicitudes APROBADA o DESPACHADA con
    fecha_aprobacion dentro del mes.
    """
    from solicitudes.models import Solicitud

    inicio_mes = _primer_dia_mes_actual_aware()

    usado = Solicitud.objects.filter(
        consumidor=consumidor,
        estado__in=ESTADOS_QUE_CONSUMEN_CUPO,
        fecha_aprobacion__gte=inicio_mes,
    ).aggregate(total=Sum("litros_aprobados"))["total"] or 0

    disponible = max(0, CUPO_MENSUAL_LITROS - usado)

    return {
        "total": CUPO_MENSUAL_LITROS,
        "usado": usado,
        "disponible": disponible,
        "mes": timezone.localdate().strftime("%Y-%m"),
    }


def obtener_solicitud_activa(consumidor):
    """
    Solicitud en curso del consumidor, si existe. Estados considerados
    activos: los mismos que protege unique_solicitud_activa_por_consumidor.
    Devuelve None si no tiene ninguna.
    """
    from solicitudes.models import Solicitud

    return (
        Solicitud.objects
        .filter(consumidor=consumidor, estado__in=ESTADOS_ACTIVOS)
        .first()
    )


def verificar_puede_crear_solicitud(consumidor, litros: int) -> tuple[bool, str]:
    """
    Chequeo previo a crear una Solicitud. No reemplaza la constraint de
    BD (que sigue siendo la garantía dura contra condiciones de carrera)
    ni la validación de litros por solicitud individual del serializer —
    esto cubre las dos reglas de negocio que SolicitudCreateSerializer
    no puede resolver por sí solo: unicidad de activa y cupo mensual.
    """
    activa = obtener_solicitud_activa(consumidor)
    if activa is not None:
        return False, (
            f"Ya tienes una solicitud activa (#{str(activa.id_publico)[:8].upper()} "
            f"en estado {activa.get_estado_display()}). No puedes crear otra "
            f"hasta que se cierre."
        )

    cupo = calcular_cupo_mensual(consumidor)
    if litros > cupo["disponible"]:
        return False, (
            f"Excederías tu cupo mensual. Ya tienes {cupo['usado']}L "
            f"aprobados/despachados de tus {cupo['total']}L. "
            f"Máximo disponible: {cupo['disponible']}L."
        )

    return True, ""


def verificar_puede_aprobar(solicitud, litros_aprobados: int) -> tuple[bool, str]:
    """
    Chequeo previo a aprobar una Solicitud. La solicitud que se está
    aprobando todavía no tiene fecha_aprobacion, así que no se
    autocuenta en calcular_cupo_mensual — el resultado ya es el
    acumulado "previo" contra el que hay que comparar litros_aprobados.
    """
    cupo = calcular_cupo_mensual(solicitud.consumidor)
    if litros_aprobados > cupo["disponible"]:
        return False, (
            f"El consumidor excedería su cupo mensual. "
            f"Acumulado: {cupo['usado']}L. "
            f"Máximo aprobable: {cupo['disponible']}L."
        )

    return True, ""
