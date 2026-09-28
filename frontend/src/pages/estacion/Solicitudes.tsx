// src/pages/estacion/Solicitudes.tsx

import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import Layout from "../../components/Layout";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { Spinner } from "../../components/ui/Spinner";
import { Modal } from "../../components/ui/Modal";
import { solicitudesService } from "../../services/solicitudes.service";
import type { Solicitud } from "../../types/solicitud.types";
import { COMBUSTIBLES } from "../../utils/constants";
import { formatFecha, formatIdPublico, fechaLocalISO } from "../../utils/format";
import { useAuth } from "../../context/AuthContext";
import type { LucideIcon } from "lucide-react";
import {
  FileText, RefreshCw, Search, Truck, Droplets,
  Clock, AlertTriangle, CheckCircle2, ChevronDown, IdCard, Building2,
} from "lucide-react";

// ------------------------------------------------
// CONSTANTES
// ------------------------------------------------

const AUTO_REFRESH_MS = 60_000;   // La estación recibe aprobaciones nuevas
                                  // mientras el operador trabaja.
const ALERT_TIMEOUT   = 5000;

// ------------------------------------------------
// HELPER — urgencia según tiempo restante
// ------------------------------------------------

type Urgencia = "ok" | "advertencia" | "critico" | "vencido";

const tiempoRestante = (fecha: string | null): { horas: number; urgencia: Urgencia } => {
  if (!fecha) return { horas: 0, urgencia: "ok" };
  const diff  = new Date(fecha).getTime() - Date.now();
  const horas = Math.floor(diff / (1000 * 60 * 60));

  if (diff <= 0)   return { horas: 0, urgencia: "vencido" };
  if (horas <= 6)  return { horas,    urgencia: "critico" };
  if (horas <= 24) return { horas,    urgencia: "advertencia" };
  return             { horas,          urgencia: "ok" };
};

// El acento de urgencia va en el borde izquierdo, no en el fondo:
// así la tarjeta mantiene fondo blanco y el CI del consumidor
// (el dato que el operador coteja) queda legible.
const urgenciaConfig: Record<Urgencia, {
  borde: string; chip: string; icono: LucideIcon; label: (h: number) => string;
}> = {
  ok: {
    borde: "border-l-primary",
    chip:  "bg-state-success-bg text-state-success-fg",
    icono: CheckCircle2,
    label: h => `${h}h`,
  },
  advertencia: {
    borde: "border-l-state-warning-fg",
    chip:  "bg-state-warning-bg text-state-warning-fg",
    icono: Clock,
    label: h => `${h}h`,
  },
  critico: {
    borde: "border-l-state-danger-fg",
    chip:  "bg-state-danger-bg text-state-danger-fg",
    icono: AlertTriangle,
    label: h => `${h}h restantes`,
  },
  vencido: {
    borde: "border-l-border",
    chip:  "bg-background text-muted-foreground",
    icono: AlertTriangle,
    label: () => "Vencida",
  },
};

// ------------------------------------------------
// COMPONENTE PRINCIPAL
// ------------------------------------------------

export default function SolicitudesESS() {
  const { user } = useAuth();

  const [solicitudes,   setSolicitudes]   = useState<Solicitud[]>([]);
  const [loading,       setLoading]       = useState(true);
  const [refrescando,   setRefrescando]   = useState(false);
  const [errorPagina,   setErrorPagina]   = useState("");
  const [despachadasHoy, setDespachadasHoy] = useState(0);
  const [busqueda,      setBusqueda]      = useState("");
  const [mostrarVencidas, setMostrarVencidas] = useState(false);

  // Alerta de éxito con auto-dismiss
  const [exito, setExito] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flashExito = (msg: string) => {
    setExito(msg);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setExito(""), ALERT_TIMEOUT);
  };

  // Modal de despacho — mantiene su propio error para no
  // mezclarlo con el de la página.
  const [modalSolicitud,    setModalSolicitud]    = useState<Solicitud | null>(null);
  const [litrosDespachados, setLitrosDespachados] = useState(0);
  const [observacion,       setObservacion]       = useState("");
  const [despachando,       setDespachando]       = useState(false);
  const [errorModal,        setErrorModal]        = useState("");

  // ------------------------------------------------
  // CARGA DE DATOS
  // ------------------------------------------------

  const cargar = useCallback(async (silencioso = false) => {
    // Sin estación asignada, el backend siempre devuelve vacío
    // (get_queryset() aísla al operador) — evitamos el round-trip
    // inútil cada 60s del auto-refresh.
    if (!user?.perfil_funcionario?.estacion_servicio) {
      setLoading(false);
      setRefrescando(false);
      return;
    }
    if (silencioso) setRefrescando(true); else setLoading(true);
    setErrorPagina("");
    try {
      const hoy = fechaLocalISO();

      const [pendientes, despachadas] = await Promise.all([
        solicitudesService.getAll({ estado: "APROBADA", ordering: "fecha_expiracion" }),
        solicitudesService.getAll({ estado: "DESPACHADA", despacho_desde: hoy }),
      ]);

      setSolicitudes(pendientes.results ?? []);
      setDespachadasHoy(despachadas.count ?? 0);
    } catch {
      setErrorPagina("Error al cargar las solicitudes.");
    } finally {
      setLoading(false);
      setRefrescando(false);
    }
  }, [user?.perfil_funcionario?.estacion_servicio]);

  useEffect(() => { cargar(); }, [cargar]);

  // Auto-refresh silencioso: no muestra spinner ni pierde la
  // posición de scroll mientras el operador atiende.
  useEffect(() => {
    const id = setInterval(() => {
      if (!modalSolicitud) cargar(true);
    }, AUTO_REFRESH_MS);
    return () => clearInterval(id);
  }, [cargar, modalSolicitud]);

  // ------------------------------------------------
  // FILTRADO LOCAL
  // Instantáneo mientras el operador escribe — con un cliente
  // esperando, pulsar "Buscar" y esperar al backend sobra.
  // ------------------------------------------------

  const { vigentes, vencidas } = useMemo(() => {
    const q = busqueda.trim().toLowerCase();

    const coincide = (s: Solicitud) => {
      if (!q) return true;
      return (
        s.id_publico.toLowerCase().includes(q) ||
        (s.consumidor_nombre ?? "").toLowerCase().includes(q) ||
        (s.consumidor_documento ?? "").toLowerCase().includes(q)
      );
    };

    const v:  Solicitud[] = [];
    const ve: Solicitud[] = [];

    solicitudes.filter(coincide).forEach(s => {
      if (tiempoRestante(s.fecha_expiracion).urgencia === "vencido") ve.push(s);
      else v.push(s);
    });

    v.sort((a, b) =>
      new Date(a.fecha_expiracion ?? "").getTime() -
      new Date(b.fecha_expiracion ?? "").getTime()
    );

    return { vigentes: v, vencidas: ve };
  }, [solicitudes, busqueda]);

  const totalLitros = vigentes.reduce((acc, s) => acc + (s.litros_aprobados ?? 0), 0);
  const urgentes    = vigentes.filter(
    s => tiempoRestante(s.fecha_expiracion).urgencia === "critico"
  ).length;

  // ------------------------------------------------
  // DESPACHO
  // ------------------------------------------------

  const abrirDespacho = (s: Solicitud) => {
    setModalSolicitud(s);
    setLitrosDespachados(s.litros_aprobados ?? 0);
    setObservacion("");
    setErrorModal("");
  };

  const confirmarDespacho = async () => {
    if (!modalSolicitud) return;
    const max = modalSolicitud.litros_aprobados ?? 0;

    if (!Number.isInteger(litrosDespachados) || litrosDespachados <= 0) {
      setErrorModal("Ingresa una cantidad válida de litros.");
      return;
    }
    if (litrosDespachados > max) {
      setErrorModal(`No puedes despachar más de ${max} L aprobados.`);
      return;
    }

    setDespachando(true);
    setErrorModal("");
    try {
      await solicitudesService.despachar(modalSolicitud.id_publico, {
        litros_despachados: litrosDespachados,
        observacion,
      });
      const combustible = COMBUSTIBLES[modalSolicitud.tipo_combustible_aprobado ?? ""] ?? "combustible";
      flashExito(
        `Despacho registrado — #${formatIdPublico(modalSolicitud.id_publico)} · ${litrosDespachados} L de ${combustible}.`
      );
      setModalSolicitud(null);
      await cargar(true);
    } catch (err: unknown) {
      const e = err as { response?: { data?: unknown } };
      const d = e.response?.data;
      let msg = "Error al despachar la solicitud.";
      if (typeof d === "string") {
        msg = d;
      } else if (d && typeof d === "object") {
        const entries = Object.entries(d as Record<string, unknown>);
        if (entries.length > 0) {
          msg = entries.map(([, v]) => (Array.isArray(v) ? v[0] : String(v))).join(" | ");
        }
      }
      setErrorModal(msg);
    } finally {
      setDespachando(false);
    }
  };

  const inputCls = "w-full px-4 py-2.5 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none";

  // ------------------------------------------------
  // TARJETA DE SOLICITUD
  // ------------------------------------------------

  const SolicitudCard = ({ s }: { s: Solicitud }) => {
    const { horas, urgencia } = tiempoRestante(s.fecha_expiracion);
    const cfg = urgenciaConfig[urgencia];
    const Icono = cfg.icono;
    const esVencida = urgencia === "vencido";

    return (
      <div className={`bg-card rounded-xl border border-border border-l-4 ${cfg.borde} shadow-sm overflow-hidden`}>
        <div className="px-4 py-3 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-mono font-semibold text-foreground">
                #{formatIdPublico(s.id_publico)}
              </span>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.chip}`}>
                <Icono className="w-3 h-3" />
                {cfg.label(horas)}
              </span>
            </div>

            <p className="text-sm font-medium text-foreground mt-1.5">
              {s.consumidor_nombre ?? "—"}
            </p>

            {/* El CI es el dato que el operador coteja contra
                el documento físico: se muestra destacado. */}
            {s.consumidor_documento && (
              <div className="inline-flex items-center gap-1.5 mt-1.5 bg-background border border-border rounded-lg px-2.5 py-1">
                <IdCard className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-sm font-semibold text-foreground tracking-wide">
                  {s.consumidor_documento}
                </span>
              </div>
            )}

            <p className="text-xs text-muted-foreground mt-1.5">
              Válido hasta {formatFecha(s.fecha_expiracion, true)}
              {s.uso_combustible ? ` · ${s.uso_combustible}` : ""}
            </p>
          </div>

          <div className="text-right shrink-0">
            <p className={`text-2xl font-bold leading-none ${esVencida ? "text-muted-foreground" : "text-state-success-fg"}`}>
              {s.litros_aprobados ?? "—"} L
            </p>
            <p className="text-xs text-muted-foreground mt-1.5">
              {COMBUSTIBLES[s.tipo_combustible_aprobado ?? ""] ?? "—"}
            </p>
            <p className="text-xs text-muted-foreground">aprobados</p>
          </div>
        </div>

        <div className="px-4 py-2.5 border-t border-border bg-background/50 flex items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">
            Aprobada {formatFecha(s.fecha_aprobacion)}
          </span>
          {esVencida ? (
            <span className="text-xs text-muted-foreground">No se puede despachar</span>
          ) : (
            <Button
              variant={urgencia === "critico" ? "danger" : "primary"}
              size="sm"
              icon={<Truck className="w-4 h-4" />}
              onClick={() => abrirDespacho(s)}
            >
              {urgencia === "critico" ? "Despachar urgente" : "Registrar despacho"}
            </Button>
          )}
        </div>
      </div>
    );
  };

  // ------------------------------------------------
  // STAT CARD
  // ------------------------------------------------

  const Stat = ({ icon: Icon, valor, label, alarma }: {
    icon: LucideIcon; valor: string | number; label: string; alarma?: boolean;
  }) => (
    <div className={`rounded-xl border shadow-sm p-4 ${
      alarma ? "bg-state-danger-bg border-state-danger-fg/20" : "bg-card border-border"
    }`}>
      <div className="flex items-center gap-3">
        <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
          alarma ? "bg-state-danger-fg/10" : "bg-primary/10"
        }`}>
          <Icon className={`w-4 h-4 ${alarma ? "text-state-danger-fg" : "text-primary"}`} />
        </div>
        <div className="min-w-0">
          <p className={`text-xl font-bold leading-none ${alarma ? "text-state-danger-fg" : "text-foreground"}`}>
            {valor}
          </p>
          <p className="text-xs text-muted-foreground mt-1 truncate">{label}</p>
        </div>
      </div>
    </div>
  );

  if (!user?.perfil_funcionario?.estacion_servicio) {
    return (
      <Layout>
        <div className="max-w-lg mx-auto text-center py-24 px-4">
          <Building2 className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h1 className="text-xl font-bold text-foreground mb-2">Sin estación asignada</h1>
          <p className="text-muted-foreground text-sm">
            Tu cuenta no tiene una estación de servicio asignada, así que no podés
            ver ni despachar solicitudes. Contacta al administrador para que te
            asigne una.
          </p>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-5">

        {/* TÍTULO */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-navbar rounded-xl flex items-center justify-center">
              <Truck className="w-5 h-5 text-navbar-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Solicitudes para despacho</h1>
              <p className="text-muted-foreground text-sm">
                {user?.estacion_nombre ?? "Estación"} · {vigentes.length} vigente(s)
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden sm:flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="w-1.5 h-1.5 rounded-full bg-state-success-fg" />
              Actualiza cada 60s
            </span>
            <Button
              variant="outline"
              icon={<RefreshCw className="w-4 h-4" />}
              loading={refrescando}
              onClick={() => cargar(true)}
            >
              Actualizar
            </Button>
          </div>
        </div>

        {/* STATS */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Stat icon={FileText}      valor={vigentes.length}   label="Pendientes" />
          <Stat icon={Droplets}      valor={`${totalLitros} L`} label="Por despachar" />
          <Stat icon={AlertTriangle} valor={urgentes}          label="Urgentes (<6h)" alarma={urgentes > 0} />
          <Stat icon={CheckCircle2}  valor={despachadasHoy}    label="Despachadas hoy" />
        </div>

        {/* ALERTAS */}
        {urgentes > 0 && (
          <Alert
            type="warning"
            message={`${urgentes} solicitud(es) vencen en menos de 6 horas. Despáchalas a la brevedad.`}
          />
        )}
        {errorPagina && <Alert type="error"   message={errorPagina} />}
        {exito       && <Alert type="success" message={exito} />}

        {/* BÚSQUEDA */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={busqueda}
            onChange={e => setBusqueda(e.target.value)}
            placeholder="Buscar por N° solicitud, nombre o CI..."
            className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-border text-sm bg-card focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none"
          />
        </div>

        {/* LISTA */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Spinner size="lg" />
          </div>
        ) : vigentes.length === 0 && vencidas.length === 0 ? (
          <Card>
            <div className="text-center py-16 px-4">
              <CheckCircle2 className="w-12 h-12 text-state-success-fg mx-auto mb-3" />
              <p className="text-foreground font-semibold">
                {busqueda ? "Sin resultados" : "Sin solicitudes pendientes"}
              </p>
              <p className="text-muted-foreground text-sm mt-1">
                {busqueda
                  ? `Ninguna solicitud coincide con "${busqueda}".`
                  : "Todas las solicitudes asignadas han sido despachadas."}
              </p>
            </div>
          </Card>
        ) : (
          <div className="space-y-3">
            {vigentes.map(s => <SolicitudCard key={s.id_publico} s={s} />)}
          </div>
        )}

        {/* VENCIDAS */}
        {vencidas.length > 0 && (
          <div>
            <button
              onClick={() => setMostrarVencidas(v => !v)}
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronDown className={`w-4 h-4 transition-transform ${mostrarVencidas ? "rotate-180" : ""}`} />
              {mostrarVencidas ? "Ocultar" : "Mostrar"} {vencidas.length} solicitud(es) vencida(s)
            </button>
            {mostrarVencidas && (
              <div className="space-y-3 mt-3">
                {vencidas.map(s => <SolicitudCard key={s.id_publico} s={s} />)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* MODAL DE DESPACHO */}
      <Modal
        open={!!modalSolicitud}
        onClose={() => setModalSolicitud(null)}
        title="Registrar despacho"
        size="sm"
      >
        {modalSolicitud && (
          <div className="space-y-4">

            {/* Verificación de identidad */}
            <div className="bg-background border border-border rounded-xl p-4">
              <p className="text-xs text-muted-foreground mb-2">
                Verifica que el documento coincida con el titular
              </p>
              <p className="text-sm font-medium text-foreground">
                {modalSolicitud.consumidor_nombre ?? "—"}
              </p>
              {modalSolicitud.consumidor_documento && (
                <div className="inline-flex items-center gap-1.5 mt-2 bg-card border border-border rounded-lg px-3 py-1.5">
                  <IdCard className="w-4 h-4 text-muted-foreground" />
                  <span className="text-base font-semibold text-foreground tracking-wide">
                    {modalSolicitud.consumidor_documento}
                  </span>
                </div>
              )}

              <div className="mt-3 pt-3 border-t border-border space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">N° Solicitud</span>
                  <span className="text-xs font-mono font-medium text-foreground">
                    #{formatIdPublico(modalSolicitud.id_publico)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-xs text-muted-foreground">Combustible</span>
                  <span className="text-xs font-medium text-foreground">
                    {COMBUSTIBLES[modalSolicitud.tipo_combustible_aprobado ?? ""] ?? "—"}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-muted-foreground">Litros aprobados</span>
                  <span className="text-lg font-bold text-primary">
                    {modalSolicitud.litros_aprobados ?? "—"} L
                  </span>
                </div>
              </div>
            </div>

            {errorModal && <Alert type="error" message={errorModal} />}

            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">
                Litros despachados *
              </label>
              <input
                type="number"
                step={1}
                min={1}
                max={modalSolicitud.litros_aprobados ?? 120}
                value={litrosDespachados}
                onChange={e => setLitrosDespachados(Math.floor(Number(e.target.value)))}
                className={inputCls}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Máximo {modalSolicitud.litros_aprobados ?? "—"} L. Si entregas menos, registra la cantidad real.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">
                Observación (opcional)
              </label>
              <textarea
                value={observacion}
                onChange={e => setObservacion(e.target.value)}
                rows={2}
                placeholder="Notas sobre el despacho..."
                className={inputCls + " resize-none"}
              />
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <Button variant="outline" onClick={() => setModalSolicitud(null)}>
                Cancelar
              </Button>
              <Button
                variant="primary"
                icon={<Truck className="w-4 h-4" />}
                loading={despachando}
                onClick={confirmarDespacho}
              >
                Confirmar despacho
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </Layout>
  );
}