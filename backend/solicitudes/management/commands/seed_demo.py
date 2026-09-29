# apps/solicitudes/management/commands/seed_demo.py
#
# Datos de demostración: consumidores y solicitudes de los últimos 3
# meses, en todos los estados, creados por ORM directo (sin pasar por
# los services, así no se dispara ningún email).
#
#   python manage.py seed_demo --password <clave>
#   python manage.py seed_demo --limpiar
#
# Todo lo que crea usa emails @demo.anh.bo, y --limpiar borra solo eso.
# Reglas que respeta: 120 L por mes calendario por consumidor (APROBADA
# + DESPACHADA, por mes de aprobación en hora local, igual que
# validar_cupo), una sola solicitud activa por consumidor, y las activas
# con su plazo vigente al momento de correr el comando. Usa las
# estaciones ACTIVAS que ya existen; no crea estaciones.

import random
from collections import defaultdict
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from users.email_service import DOMINIO_DEMO


NOMBRES = [
    "Juan", "María", "Carlos", "Ana", "Luis", "Rosa", "Jorge", "Carmen",
    "Pedro", "Lucía", "Miguel", "Elena", "Fernando", "Silvia", "Raúl",
    "Patricia", "Diego", "Gabriela",
]
APELLIDOS = [
    "Mamani", "Quispe", "Choque", "Flores", "Condori", "Vargas", "Rojas",
    "Gutiérrez", "Fernández", "Rodríguez", "López", "Mendoza", "Torrez",
    "Pérez", "Ramírez", "Castro",
]

USO_POR_ACTIVIDAD = {
    "AGRICULTURA":  "Tractor para siembra y cosecha",
    "TRANSPORTE":   "Minibús de transporte interprovincial",
    "INDUSTRIA":    "Generador de planta de producción",
    "CONSTRUCCION": "Maquinaria de obra (mezcladora)",
    "COMERCIO":     "Camioneta de reparto",
    "MINERIA":      "Compresora de cooperativa minera",
    "DOMESTICO":    "Generador doméstico",
}

MOTIVOS_RECHAZO = [
    "La fotografía del documento es ilegible.",
    "El uso declarado no corresponde a la actividad registrada.",
    "Los datos del documento no coinciden con los del registro.",
]
OBSERVACIONES = [
    "Adjunta una fotografía legible del reverso de tu CI.",
    "Aclara el uso del combustible: no coincide con tu actividad.",
    "Indica la placa o el número de serie del equipo.",
]
MOTIVO_RECHAZO_AUTOMATICO = (
    "Rechazada automáticamente: no se respondió la observación "
    "dentro del plazo."
)

# Distribución de estados (≈50 solicitudes para 15 consumidores).
# "RECHAZADA_AUTO" es un rechazo por observación vencida.
TERMINALES = (
    ["DESPACHADA"] * 20 + ["RECHAZADA"] * 4 + ["RECHAZADA_AUTO"] * 2
    + ["CANCELADA"] * 6 + ["EXPIRADA"] * 7
)
ACTIVAS = ["PENDIENTE"] * 4 + ["OBSERVADA"] * 3 + ["APROBADA"] * 4

LITROS = [20, 25, 30, 40, 50, 60]
CUPO_MES = 120


class Command(BaseCommand):
    help = (
        f"Crea datos de demostración (emails {DOMINIO_DEMO}) o, con "
        f"--limpiar, los borra. No envía emails."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help="Contraseña de las cuentas de demo (obligatoria al crear).",
        )
        parser.add_argument(
            "--limpiar", action="store_true",
            help=f"Borra todos los usuarios {DOMINIO_DEMO} y sus datos.",
        )
        parser.add_argument("--consumidores", type=int, default=15)
        parser.add_argument(
            "--semilla", type=int, default=2026,
            help="Semilla aleatoria (mismos datos en cada corrida).",
        )

    # ------------------------------------------------
    # ENTRADA
    # ------------------------------------------------

    def handle(self, *args, **opts):
        if opts["limpiar"]:
            self._limpiar()
            return

        password = opts["password"]
        if not password or len(password) < 8:
            raise CommandError("Pasa --password con al menos 8 caracteres.")

        from users.models import User
        if User.objects.filter(email__iendswith=DOMINIO_DEMO).exists():
            raise CommandError(
                f"Ya hay datos de demo ({DOMINIO_DEMO}). "
                f"Corre primero: python manage.py seed_demo --limpiar"
            )

        from estaciones.models import EstacionServicio
        estaciones = list(
            EstacionServicio.objects.filter(estado="ACTIVA")
            .select_related("municipio__provincia__departamento")
        )
        if not estaciones:
            raise CommandError("No hay estaciones ACTIVAS: el seed usa las existentes.")

        self.rng   = random.Random(opts["semilla"])
        # Generador aparte para los CI: la secuencia de números no
        # depende de cuántos sorteos hagan las fechas/estados.
        self.rng_ci = random.Random(opts["semilla"] + 1)
        self.ci_usados = set()
        self.ahora = timezone.now()

        from configuracion.models import ConfiguracionSistema
        self.horas_expiracion = ConfiguracionSistema.obtener().tiempo_expiracion_solicitudes_horas

        with transaction.atomic():
            resumen = self._crear(opts["consumidores"], password, estaciones)

        self.stdout.write(self.style.SUCCESS(
            f"Demo creada: {resumen['consumidores']} consumidores, "
            f"{resumen['solicitudes']} solicitudes."
        ))
        for estado, n in sorted(resumen["por_estado"].items()):
            self.stdout.write(f"  {estado:<11} {n}")

    # ------------------------------------------------
    # LIMPIAR
    # ------------------------------------------------

    def _limpiar(self):
        from users.models import User
        from solicitudes.models import Solicitud, AuditoriaEstadoSolicitud

        usuarios    = User.objects.filter(email__iendswith=DOMINIO_DEMO)
        solicitudes = Solicitud.objects.filter(consumidor__user__in=usuarios)

        with transaction.atomic():
            # Orden por los PROTECT: auditoría → solicitudes → usuarios
            # (perfil, documentos y tokens caen en cascada con el user).
            n_aud = AuditoriaEstadoSolicitud.objects.filter(solicitud__in=solicitudes).delete()[0]
            n_sol = solicitudes.delete()[0]
            n_usr = usuarios.count()
            usuarios.delete()

        self.stdout.write(self.style.SUCCESS(
            f"Demo borrada: {n_usr} usuarios, {n_sol} solicitudes, "
            f"{n_aud} registros de auditoría."
        ))

    # ------------------------------------------------
    # CREAR
    # ------------------------------------------------

    def _crear(self, n_consumidores, password, estaciones):
        from users.models import User

        self.aprobador = (
            User.objects.filter(
                tipo_usuario__in=[User.TipoUsuario.ANH, User.TipoUsuario.ADMIN],
                estado_cuenta=User.EstadoCuenta.ACTIVO,
            ).exclude(email__iendswith=DOMINIO_DEMO).first()
        )

        terminales = TERMINALES[:]
        activas    = ACTIVAS[:]
        self.rng.shuffle(terminales)
        self.rng.shuffle(activas)

        # Reparto round-robin: cada consumidor recibe 2-3 terminales;
        # los primeros len(activas) reciben además una activa.
        plan = defaultdict(list)
        for i, estado in enumerate(terminales):
            plan[i % n_consumidores].append(estado)

        por_estado = defaultdict(int)
        total = 0
        for i in range(n_consumidores):
            perfil, estacion = self._crear_consumidor(i, password, estaciones)
            self.usado = defaultdict(int)  # (año, mes) → litros

            fechas = self._fechas_historicas(len(plan[i]))
            for estado, t0 in zip(plan[i], fechas):
                final = self._crear_terminal(perfil, estacion, estado, t0)
                por_estado[final] += 1
                total += 1

            if i < len(activas):
                final = self._crear_activa(perfil, estacion, activas[i])
                por_estado[final] += 1
                total += 1

        return {
            "consumidores": n_consumidores,
            "solicitudes":  total,
            "por_estado":   por_estado,
        }

    def _crear_consumidor(self, i, password, estaciones):
        from users.models import User
        from consumidores.models import ConsumidorPerfil, DocumentoIdentidad

        nombre   = NOMBRES[i % len(NOMBRES)]
        apellido = APELLIDOS[(i * 7) % len(APELLIDOS)]
        materno  = APELLIDOS[(i * 3 + 5) % len(APELLIDOS)]
        email    = (
            f"{_slug(nombre)}.{_slug(apellido)}.{i + 1:02d}{DOMINIO_DEMO}"
        )

        user = User.objects.create_user(
            email=email, nombres=nombre, apellido_paterno=apellido,
            apellido_materno=materno, tipo_usuario=User.TipoUsuario.CONS,
            password=password,
        )
        user.estado_cuenta    = User.EstadoCuenta.ACTIVO
        user.email_verificado = True
        user.save(update_fields=["estado_cuenta", "email_verificado"])

        estacion  = estaciones[i % len(estaciones)]
        municipio = estacion.municipio
        actividad = self.rng.choice(list(USO_POR_ACTIVIDAD))

        perfil = ConsumidorPerfil.objects.create(
            user=user,
            fecha_nacimiento=date(1965 + (i * 3) % 35, 1 + i % 12, 1 + (i * 5) % 28),
            celular=f"7{i + 1:07d}",
            departamento=municipio.provincia.departamento,
            provincia=municipio.provincia,
            municipio=municipio,
            direccion=f"Calle {i + 1} #{100 + i * 13}",
            actividad=actividad,
            estado_identidad=ConsumidorPerfil.EstadoIdentidad.VERIFICADO,
        )
        # Sin imágenes: son datos de demo (el detalle muestra el
        # documento sin fotos).
        DocumentoIdentidad.objects.create(
            perfil=perfil,
            tipo_documento=DocumentoIdentidad.TipoDocumento.CI,
            numero_documento=self._ci_libre(),
            anverso="", reverso="",
        )
        return perfil, estacion

    def _ci_libre(self) -> str:
        """
        CI realista de 7-8 dígitos que no exista en ningún documento
        (consumidores ni funcionarios) ni en los ya generados. La demo
        se identifica por el email, no por el CI.
        """
        from consumidores.models import DocumentoIdentidad
        from users.models import PerfilFuncionario

        while True:
            ci = str(self.rng_ci.randint(1_000_000, 99_999_999))
            if ci in self.ci_usados:
                continue
            if DocumentoIdentidad.objects.filter(numero_documento=ci).exists():
                continue
            if PerfilFuncionario.objects.filter(numero_documento=ci).exists():
                continue
            self.ci_usados.add(ci)
            return ci

    # ------------------------------------------------
    # FECHAS
    # ------------------------------------------------

    def _fechas_historicas(self, k):
        """
        k fechas de creación en orden, entre hace ~88 días y hace 3
        días, una por tramo igual: nunca se superponen dos solicitudes
        del mismo consumidor (cada ciclo dura menos que un tramo).
        """
        if k == 0:
            return []
        inicio = self.ahora - timedelta(days=88)
        fin    = self.ahora - timedelta(days=3)
        tramo  = (fin - inicio) / k
        return [
            inicio + tramo * j + tramo * self.rng.uniform(0.05, 0.6)
            for j in range(k)
        ]

    def _horas(self, a, b):
        return timedelta(hours=self.rng.uniform(a, b))

    # ------------------------------------------------
    # CUPO
    # ------------------------------------------------

    def _litros_aprobables(self, solicitados, fecha_aprobacion):
        local = timezone.localtime(fecha_aprobacion)
        clave = (local.year, local.month)
        disponible = CUPO_MES - self.usado[clave]
        if disponible < 10:
            return None
        return min(solicitados, disponible)

    def _consumir(self, litros, fecha_aprobacion):
        local = timezone.localtime(fecha_aprobacion)
        self.usado[(local.year, local.month)] += litros

    # ------------------------------------------------
    # SOLICITUDES
    # ------------------------------------------------

    def _base(self, perfil, estacion, t0):
        from solicitudes.models import Solicitud
        return dict(
            consumidor=perfil,
            creado_por=perfil.user,
            estacion_servicio=estacion,
            tipo_combustible=self.rng.choice(
                [Solicitud.TipoCombustible.GASOLINA, Solicitud.TipoCombustible.DIESEL]
            ),
            litros_solicitados=self.rng.choice(LITROS),
            departamento=perfil.departamento,
            provincia=perfil.provincia,
            municipio=perfil.municipio,
            direccion=perfil.direccion,
            actividad=perfil.actividad,
            uso_combustible=USO_POR_ACTIVIDAD.get(perfil.actividad, "Uso declarado"),
            declaracion_jurada_confirmada=True,
            fecha_declaracion_jurada=t0,
        )

    def _crear_terminal(self, perfil, estacion, estado, t0):
        from solicitudes.models import Solicitud
        E = Solicitud.EstadoSolicitud
        datos = self._base(perfil, estacion, t0)
        auditoria = []

        if estado in ("DESPACHADA", "EXPIRADA"):
            aprob = t0 + self._horas(2, 20)
            litros = self._litros_aprobables(datos["litros_solicitados"], aprob)
            if litros is None:
                estado = "CANCELADA"  # sin cupo ese mes: el consumidor la canceló
            else:
                exp = aprob + timedelta(hours=self.horas_expiracion)
                datos.update(
                    tipo_combustible_aprobado=datos["tipo_combustible"],
                    litros_aprobados=litros, aprobado_por=self.aprobador,
                    fecha_revision=aprob, fecha_aprobacion=aprob,
                    fecha_asignacion_estacion=aprob, fecha_expiracion=exp,
                )
                auditoria.append((E.PENDIENTE, E.APROBADA, self.aprobador, aprob, "Aprobada."))
                if estado == "DESPACHADA":
                    desp = aprob + self._horas(0.5, max(0.6, self.horas_expiracion * 0.8))
                    operador = estacion.funcionarios.select_related("user").first()
                    parcial = self.rng.random() < 0.15
                    datos.update(
                        estado=E.DESPACHADA,
                        litros_despachados=litros - 5 if parcial and litros > 10 else litros,
                        observacion_despacho="Despacho parcial por stock." if parcial and litros > 10 else "",
                        despachado_por=operador.user if operador else None,
                        fecha_despacho=desp,
                    )
                    self._consumir(litros, aprob)
                    auditoria.append((E.APROBADA, E.DESPACHADA, operador.user if operador else None, desp, "Despacho registrado."))
                    fin = desp
                else:
                    datos["estado"] = E.EXPIRADA
                    auditoria.append((E.APROBADA, E.EXPIRADA, None, exp, "Expirada automáticamente por el sistema."))
                    fin = exp

        if estado == "RECHAZADA":
            rev = t0 + self._horas(3, 30)
            motivo = self.rng.choice(MOTIVOS_RECHAZO)
            datos.update(estado=E.RECHAZADA, observacion_anh=motivo, fecha_revision=rev)
            auditoria.append((E.PENDIENTE, E.RECHAZADA, self.aprobador, rev, f"Rechazo: {motivo}"))
            fin = rev
        elif estado == "RECHAZADA_AUTO":
            obs = t0 + self._horas(3, 20)
            limite = obs + timedelta(hours=24)
            datos.update(
                estado=E.RECHAZADA, observacion_anh=MOTIVO_RECHAZO_AUTOMATICO,
                fecha_observacion=obs, fecha_limite_respuesta=limite,
            )
            auditoria.append((E.PENDIENTE, E.OBSERVADA, self.aprobador, obs,
                              f"Observación: {self.rng.choice(OBSERVACIONES)}"))
            auditoria.append((E.OBSERVADA, E.RECHAZADA, None, limite + self._horas(0.1, 3),
                              "Rechazada automáticamente por no responder la observación dentro del plazo de 24 horas."))
            fin = auditoria[-1][3]
            estado = "RECHAZADA"
        elif estado == "CANCELADA":
            canc = t0 + self._horas(1, 24)
            datos["estado"] = E.CANCELADA
            auditoria.append((E.PENDIENTE, E.CANCELADA, perfil.user, canc, "Cancelada por el consumidor."))
            fin = canc

        self._guardar(datos, t0, fin, auditoria)
        return estado

    def _crear_activa(self, perfil, estacion, estado):
        from solicitudes.models import Solicitud
        E = Solicitud.EstadoSolicitud
        auditoria = []

        if estado == "PENDIENTE":
            t0 = self.ahora - self._horas(1, 30)
            datos = self._base(perfil, estacion, t0)
            fin = t0

        elif estado == "OBSERVADA":
            obs = self.ahora - self._horas(1, 12)          # plazo: obs + 24 h > ahora
            t0  = obs - self._horas(2, 20)
            datos = self._base(perfil, estacion, t0)
            texto = self.rng.choice(OBSERVACIONES)
            datos.update(
                estado=E.OBSERVADA, observacion_anh=texto, fecha_revision=obs,
                fecha_observacion=obs, fecha_limite_respuesta=obs + timedelta(hours=24),
            )
            auditoria.append((E.PENDIENTE, E.OBSERVADA, self.aprobador, obs, f"Observación: {texto}"))
            fin = obs

        else:  # APROBADA, vigente: aprobada hace menos de la mitad del plazo
            aprob = self.ahora - timedelta(hours=self.horas_expiracion * self.rng.uniform(0.05, 0.45))
            t0 = aprob - self._horas(2, 20)
            datos = self._base(perfil, estacion, t0)
            litros = self._litros_aprobables(datos["litros_solicitados"], aprob)
            if litros is None:
                # Sin cupo este mes: queda como pendiente
                datos = self._base(perfil, estacion, t0)
                self._guardar(datos, t0, t0, [])
                return "PENDIENTE"
            datos.update(
                estado=E.APROBADA, tipo_combustible_aprobado=datos["tipo_combustible"],
                litros_aprobados=litros, aprobado_por=self.aprobador,
                fecha_revision=aprob, fecha_aprobacion=aprob, fecha_asignacion_estacion=aprob,
                fecha_expiracion=aprob + timedelta(hours=self.horas_expiracion),
            )
            self._consumir(litros, aprob)
            auditoria.append((E.PENDIENTE, E.APROBADA, self.aprobador, aprob, "Aprobada."))
            fin = aprob

        self._guardar(datos, t0, fin, auditoria)
        return estado

    def _guardar(self, datos, t0, fin, auditoria):
        from solicitudes.models import Solicitud, AuditoriaEstadoSolicitud

        s = Solicitud.objects.create(**datos)
        # fecha_creacion/fecha_actualizacion son auto_now(_add): se pisan
        # con update() para ubicar la solicitud en el pasado.
        Solicitud.objects.filter(pk=s.pk).update(fecha_creacion=t0, fecha_actualizacion=fin)

        for anterior, nuevo, usuario, fecha, nota in auditoria:
            a = AuditoriaEstadoSolicitud.objects.create(
                solicitud=s, estado_anterior=anterior, estado_nuevo=nuevo,
                usuario=usuario, nota=nota,
            )
            AuditoriaEstadoSolicitud.objects.filter(pk=a.pk).update(fecha=fecha)


def _slug(texto):
    reemplazos = str.maketrans("áéíóúñÁÉÍÓÚÑ", "aeiounAEIOUN")
    return texto.translate(reemplazos).lower()
