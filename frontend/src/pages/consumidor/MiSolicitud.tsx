// src/pages/consumidor/MiSolicitud.tsx

import { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import Layout from "../../components/Layout";
import { EstadoSolicitudBadge } from "../../components/ui/EstadoBadge";
import { CupoMensualWidget } from "../../components/ui/CupoMensualWidget";
import { useAuth } from "../../context/AuthContext";
import { solicitudesService } from "../../services/solicitudes.service";
import { estacionesService } from "../../services/estaciones.service";
import { catalogosService } from "../../services/catalogos.service";
import type { Solicitud } from "../../types/solicitud.types";
import { COMBUSTIBLES } from "../../utils/constants";
import { formatFecha, formatIdPublico } from "../../utils/format";
import {
  FileText, Plus, X, Download, AlertCircle,
  CheckCircle, Clock, ChevronDown, ChevronUp,
  MessageSquare, AlertTriangle, Send
} from "lucide-react";
import PDFViewer from "../../components/ui/PDFViewer";

// ------------------------------------------------
// SCHEMAS
// ------------------------------------------------

const schema = z.object({
  tipo_combustible:              z.string().min(1, "Selecciona el tipo de combustible"),
  litros_solicitados:            z.number().int().min(1).max(120),
  uso_combustible:               z.string().min(10, "Describe el uso (mínimo 10 caracteres)").max(200),
  declaracion_jurada_confirmada: z.boolean(),
  departamento:                  z.number().int().positive("Selecciona el departamento"),
  provincia:                     z.number().int().positive("Selecciona la provincia"),
  municipio:                     z.number().int().positive("Selecciona el municipio"),
  estacion_servicio:             z.number().int().positive("Selecciona una estación de servicio"),
});

const respuestaSchema = z.object({
  respuesta: z.string().min(10, "La respuesta debe tener al menos 10 caracteres").max(500),
});

type FormData = {
  tipo_combustible:              string;
  litros_solicitados:            number;
  uso_combustible:               string;
  declaracion_jurada_confirmada: boolean;
  departamento:                  number;
  provincia:                     number;
  municipio:                     number;
  estacion_servicio:             number;
};

type RespuestaData = z.infer<typeof respuestaSchema>;

interface Opcion { id: number; nombre: string; }

// ------------------------------------------------
// HELPERS — countdown
// ------------------------------------------------
const horasRestantes = (fechaLimite: string | null): number => {
  if (!fechaLimite) return 0;
  const diff = new Date(fechaLimite).getTime() - Date.now();
  if (diff <= 0) return 0;
  return Math.floor(diff / (1000 * 60 * 60));
};

const minutosRestantes = (fechaLimite: string | null): number => {
  if (!fechaLimite) return 0;
  const diff = new Date(fechaLimite).getTime() - Date.now();
  if (diff <= 0) return 0;
  return Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
};

// ------------------------------------------------
// COMPONENTE
// ------------------------------------------------

export default function MiSolicitud() {
  const { cupo, refreshCupo } = useAuth();
  // Con el cupo agotado el submit queda deshabilitado; si el cupo no
  // se pudo cargar (null) no se bloquea — el backend valida igual.
  const sinCupo = cupo !== null && cupo.disponible <= 0;
  const [solicitudActiva,  setSolicitudActiva]  = useState<Solicitud | null>(null);
  const [historial,        setHistorial]        = useState<Solicitud[]>([]);
  const [loading,          setLoading]          = useState(true);
  const [creando,          setCreando]          = useState(false);
  const [respondiendo,     setRespondiendo]     = useState(false);
  const [mostrarForm,      setMostrarForm]      = useState(false);
  const [mostrarRespuesta, setMostrarRespuesta] = useState(false);
  const [mostrarHistorial, setMostrarHistorial] = useState(false);
  const [error,            setError]            = useState("");
  const [exito,            setExito]            = useState("");
  const [docJustificativo, setDocJustificativo] = useState<File | null>(null);
  const [pdfViewer,        setPdfViewer]        = useState<"declaracion" | "comprobante" | null>(null);
  const [docRespuesta,     setDocRespuesta]     = useState<File | null>(null);

  const [deptos, setDeptos] = useState<Opcion[]>([]);
  const [provs,  setProvs]  = useState<Opcion[]>([]);
  const [munis,  setMunis]  = useState<Opcion[]>([]);
  const [estaciones, setEstaciones] = useState<Opcion[]>([]);
  const [cargandoCatalogo, setCargandoCatalogo] = useState(false);

  const {
    register, handleSubmit, reset, setValue, watch,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      tipo_combustible:              "",
      litros_solicitados:            1,
      uso_combustible:               "",
      declaracion_jurada_confirmada: false,
      departamento:                  0,
      provincia:                     0,
      municipio:                     0,
      estacion_servicio:             0,
    }
  });

  const formRespuesta = useForm<RespuestaData>({
    resolver: zodResolver(respuestaSchema),
    defaultValues: { respuesta: "" },
  });

  // ------------------------------------------------
  // CARGAR
  // ------------------------------------------------
  const cargar = async () => {
    setLoading(true);
    try {
      const todas = await solicitudesService.getMisSolicitudes();
      const activaBasic = todas.find(s =>
        ["PENDIENTE", "OBSERVADA", "APROBADA"].includes(s.estado)
      ) ?? null;

      if (activaBasic) {
        const detalle = await solicitudesService.getById(activaBasic.id_publico);
        setSolicitudActiva(detalle);
      } else {
        setSolicitudActiva(null);
      }

      setHistorial(todas.filter(s =>
        !["PENDIENTE", "OBSERVADA", "APROBADA"].includes(s.estado)
      ));
    } catch {
      setError("Error al cargar las solicitudes.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  // "Al montar el dashboard" — MiSolicitud es la pantalla de inicio
  // del consumidor (RoleRedirect lo manda acá). Sin force: respeta
  // el cache de 5 min si vino fresco desde el login.
  useEffect(() => { refreshCupo(); }, [refreshCupo]);

  useEffect(() => {
    catalogosService.getDepartamentos()
      .then(setDeptos)
      .catch(() => {});
  }, []);

  // ------------------------------------------------
  // CASCADA UBICACIÓN
  // ------------------------------------------------

  const onDeptoChange = async (deptoId: number) => {
    setValue("departamento", deptoId);
    setValue("provincia", 0);
    setValue("municipio", 0);
    setValue("estacion_servicio", 0);
    setProvs([]); setMunis([]); setEstaciones([]);
    if (!deptoId) return;
    setCargandoCatalogo(true);
    try {
      const data = await catalogosService.getProvincias(deptoId);
      setProvs(data);
    } finally { setCargandoCatalogo(false); }
  };

  const onProvChange = async (provId: number) => {
    setValue("provincia", provId);
    setValue("municipio", 0);
    setValue("estacion_servicio", 0);
    setMunis([]); setEstaciones([]);
    if (!provId) return;
    setCargandoCatalogo(true);
    try {
      const data = await catalogosService.getMunicipios(provId);
      setMunis(data);
    } finally { setCargandoCatalogo(false); }
  };

  const onMuniChange = async (muniId: number) => {
    setValue("municipio", muniId);
    setValue("estacion_servicio", 0);
    setEstaciones([]);
    if (!muniId) return;
    setCargandoCatalogo(true);
    try {
      const data = await estacionesService.getAll({ municipio: String(muniId), estado: "ACTIVA" });
      const lista = Array.isArray(data) ? data : (data as any).results ?? [];
      setEstaciones(lista.map((e: any) => ({ id: e.id, nombre: e.nombre })));
    } finally { setCargandoCatalogo(false); }
  };

  // ------------------------------------------------
  // CREAR SOLICITUD
  // ------------------------------------------------
  const onSubmit = async (data: FormData) => {
    setCreando(true);
    setError("");
    if (!data.declaracion_jurada_confirmada) {
      setError("Debes confirmar la declaración jurada.");
      setCreando(false);
      return;
    }
    // Validación pre-submit contra el cupo cacheado — el backend es la
    // fuente de verdad (puede haber cambiado entre que se cargó el
    // widget y el submit), pero evita un viaje al servidor para el
    // caso obvio de que ya se ve en pantalla que no alcanza.
    if (cupo && data.litros_solicitados > cupo.disponible) {
      setError(
        `Excederías tu cupo mensual. Ya tienes ${cupo.usado}L aprobados/despachados ` +
        `de tus ${cupo.total_mes}L. Máximo disponible: ${cupo.disponible}L.`
      );
      setCreando(false);
      return;
    }
    try {
      await solicitudesService.crear({
        tipo_combustible:              data.tipo_combustible as import("../../types/solicitud.types").TipoCombustible,
        litros_solicitados:            data.litros_solicitados,
        uso_combustible:               data.uso_combustible,
        declaracion_jurada_confirmada: true,
        documento_justificativo:       docJustificativo,
        departamento:                  data.departamento,
        provincia:                     data.provincia,
        municipio:                      data.municipio,
        estacion_servicio:              data.estacion_servicio,
      });
      setExito("¡Solicitud creada exitosamente! La ANH revisará tu solicitud.");
      setMostrarForm(false);
      reset();
      setProvs([]); setMunis([]); setEstaciones([]);
      await cargar();
      await refreshCupo({ force: true });
    } catch (err: unknown) {
      const e = err as { response?: { data?: Record<string, string[]> | { detail?: string } } };
      const data2 = e.response?.data;
      if (data2 && "detail" in data2) {
        const detail = (data2 as { detail?: string }).detail;
        setError(Array.isArray(detail) ? detail[0] : (detail ?? "Error al crear la solicitud."));
      } else if (data2) {
        const msgs = Object.entries(data2 as Record<string, unknown>)
          .map(([k, v]) => Array.isArray(v) ? `${k}: ${v[0]}` : `${k}: ${String(v)}`)
          .join(" | ");
        setError(msgs);
      } else {
        setError("Error al crear la solicitud.");
      }
      // El 400 puede ser justo por exceder cupo (o porque ANH aprobó
      // algo mientras el consumidor tenía el formulario abierto) —
      // se resincroniza para que el widget no quede mostrando un
      // disponible que ya no es real.
      await refreshCupo({ force: true });
    } finally {
      setCreando(false);
    }
  };

  // ------------------------------------------------
  // RESPONDER OBSERVACIÓN
  // ------------------------------------------------
  const onResponder = async (data: RespuestaData) => {
    if (!solicitudActiva) return;
    setRespondiendo(true);
    setError("");
    try {
      await solicitudesService.responderObservacion(
        solicitudActiva.id_publico,
        data.respuesta,
        docRespuesta,
      );
      setExito(
        "¡Respuesta enviada! Tu solicitud volvió a estado Pendiente. " +
        "La ANH la revisará nuevamente."
      );
      setMostrarRespuesta(false);
      formRespuesta.reset();
      setDocRespuesta(null);
      await cargar();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      const detail = e.response?.data?.detail;
      setError(Array.isArray(detail) ? detail[0] : (detail ?? "Error al enviar la respuesta."));
    } finally {
      setRespondiendo(false);
    }
  };

  // ------------------------------------------------
  // CANCELAR
  // ------------------------------------------------
  const cancelar = async () => {
    if (!solicitudActiva) return;
    if (!confirm("¿Estás seguro de cancelar tu solicitud?")) return;
    try {
      await solicitudesService.cancelar(solicitudActiva.id_publico);
      setExito("Solicitud cancelada.");
      await cargar();
      await refreshCupo({ force: true });
    } catch {
      setError("Error al cancelar la solicitud.");
    }
  };

  const descargarComprobante = async () => {
    if (!solicitudActiva) return;
    try { await solicitudesService.descargarComprobante(solicitudActiva.id_publico); }
    catch { setError("Error al descargar el comprobante."); }
  };

  const descargarDeclaracion = async (idPublico: string) => {
    try { await solicitudesService.descargarDeclaracionJurada(idPublico); }
    catch { setError("Error al descargar la declaración jurada."); }
  };

  if (loading) return (
    <Layout>
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    </Layout>
  );

  const inputCls = (hasErr: boolean) =>
    `w-full px-4 py-2.5 rounded-xl border text-sm outline-none bg-input transition-colors ${
      hasErr ? "border-red-300" : "border-border focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card"
    }`;

  // ------------------------------------------------
  // DATOS DE OBSERVACIÓN
  // ------------------------------------------------
  const estaObservada = solicitudActiva?.estado === "OBSERVADA";
  const fechaLimite   = solicitudActiva?.fecha_limite_respuesta ?? null;
  const horas         = estaObservada ? horasRestantes(fechaLimite) : 0;
  const minutos       = estaObservada ? minutosRestantes(fechaLimite) : 0;
  const plazoVencido  = estaObservada && !!fechaLimite && new Date(fechaLimite).getTime() < Date.now();
  const porcentajeTiempo = fechaLimite
    ? Math.min(100, Math.max(0, ((horas * 60 + minutos) / (24 * 60)) * 100))
    : 0;

  const watchDepto = watch("departamento");
  const watchProv  = watch("provincia");
  const watchMuni  = watch("municipio");

  return (
    <Layout>
      <div className="max-w-2xl mx-auto space-y-6">

        {/* TÍTULO */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Mis Solicitudes</h1>
            <p className="text-muted-foreground text-sm mt-1">Gestiona tu solicitud de combustible</p>
          </div>
          {!solicitudActiva && (
            <button
              onClick={() => { setMostrarForm(!mostrarForm); setError(""); setExito(""); }}
              className="flex items-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary-hover transition-colors"
            >
              {mostrarForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
              {mostrarForm ? "Cancelar" : "Nueva solicitud"}
            </button>
          )}
        </div>

        {/* CUPO MENSUAL — entre el header y el resto (solicitud activa o formulario) */}
        {cupo && (
          <CupoMensualWidget
            usado={cupo.usado}
            total={cupo.total_mes}
            disponible={cupo.disponible}
          />
        )}

        {/* ALERTAS */}
        {error && (
          <div className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" /> <span>{error}</span>
          </div>
        )}
        {exito && (
          <div className="flex items-start gap-3 bg-state-success-bg border border-state-success-fg/20 text-state-success-fg rounded-xl px-4 py-3 text-sm">
            <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" /> <span>{exito}</span>
          </div>
        )}

        {/* BANNER OBSERVACIÓN VIGENTE */}
        {estaObservada && !plazoVencido && (
          <div className="bg-amber-50 border border-amber-300 rounded-2xl px-5 py-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="font-semibold text-amber-800 text-sm mb-1">
                  Tu solicitud fue observada por la ANH
                </p>
                <p className="text-amber-700 text-sm mb-2">
                  Tienes <strong>{horas}h {minutos}m</strong> para responder la observación.
                  Si no respondes a tiempo, la solicitud será rechazada automáticamente.
                </p>
                <div className="w-full bg-amber-200 rounded-full h-2 mb-3">
                  <div
                    className="bg-amber-500 h-2 rounded-full transition-all"
                    style={{ width: `${porcentajeTiempo}%` }}
                  />
                </div>
                <button
                  onClick={() => setMostrarRespuesta(!mostrarRespuesta)}
                  className="flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-xl text-xs font-medium transition-colors"
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  {mostrarRespuesta ? "Ocultar formulario" : "Responder observación"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* BANNER PLAZO VENCIDO */}
        {estaObservada && plazoVencido && (
          <div className="bg-red-50 border border-red-200 rounded-2xl px-5 py-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-red-700 text-sm mb-1">
                  Plazo de respuesta vencido
                </p>
                <p className="text-red-600 text-sm">
                  El plazo de 24 horas para responder ha vencido.
                  La solicitud será rechazada automáticamente en la próxima actualización del sistema.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* FORMULARIO DE RESPUESTA */}
        {estaObservada && mostrarRespuesta && !plazoVencido && (
          <div className="bg-card rounded-2xl border border-amber-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-amber-100 bg-amber-50">
              <h2 className="font-semibold text-amber-800 flex items-center gap-2 text-sm">
                <MessageSquare className="w-4 h-4" />
                Responder observación de la ANH
              </h2>
            </div>

            <div className="px-6 pt-4">
              <p className="text-xs text-muted-foreground mb-1">Observación de la ANH:</p>
              <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800 mb-4">
                {solicitudActiva?.observacion_anh
                  ? solicitudActiva.observacion_anh
                  : <span className="italic text-amber-500">Sin texto adicional</span>
                }
              </div>
            </div>

            <form onSubmit={formRespuesta.handleSubmit(onResponder)} className="px-6 pb-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">
                  Tu respuesta / justificación *
                </label>
                <textarea
                  {...formRespuesta.register("respuesta")}
                  rows={4}
                  placeholder="Explica o justifica la observación de la ANH (mínimo 10 caracteres)..."
                  className={inputCls(!!formRespuesta.formState.errors.respuesta) + " resize-none"}
                />
                {formRespuesta.formState.errors.respuesta && (
                  <p className="text-red-500 text-xs mt-1">
                    {formRespuesta.formState.errors.respuesta.message}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">
                  Adjuntar documento (opcional)
                </label>
                <label className={`flex items-center gap-3 w-full px-4 py-2.5 rounded-xl border text-sm cursor-pointer transition-colors ${
                  docRespuesta ? "border-primary bg-state-success-bg" : "border-border bg-input hover:bg-background"
                }`}>
                  <input
                    type="file"
                    accept="image/*,application/pdf"
                    className="hidden"
                    onChange={e => setDocRespuesta(e.target.files?.[0] ?? null)}
                  />
                  {docRespuesta
                    ? <><CheckCircle className="w-4 h-4 text-primary" /><span className="text-state-success-fg truncate">{docRespuesta.name}</span></>
                    : <><FileText className="w-4 h-4 text-muted-foreground" /><span className="text-muted-foreground">PDF o imagen — máx 10MB</span></>
                  }
                </label>
                {docRespuesta && (
                  <button type="button" onClick={() => setDocRespuesta(null)}
                    className="text-xs text-red-500 mt-1 hover:underline">
                    Quitar archivo
                  </button>
                )}
              </div>

              <div className="flex gap-3">
                <button type="button" onClick={() => setMostrarRespuesta(false)}
                  className="px-4 py-2.5 border border-border text-muted-foreground rounded-xl text-sm hover:bg-background transition-colors">
                  Cancelar
                </button>
                <button type="submit" disabled={respondiendo}
                  className="flex items-center gap-2 px-5 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-xl text-sm font-medium transition-colors">
                  {respondiendo
                    ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    : <Send className="w-4 h-4" />
                  }
                  {respondiendo ? "Enviando..." : "Enviar respuesta"}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* SOLICITUD ACTIVA */}
        {solicitudActiva && (
          <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-primary/10 rounded-lg flex items-center justify-center">
                  <FileText className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <p className="font-semibold text-foreground text-sm">
                    Solicitud #{formatIdPublico(solicitudActiva.id_publico)}
                  </p>
                  <p className="text-muted-foreground text-xs">
                    {formatFecha(solicitudActiva.fecha_creacion, true)}
                  </p>
                </div>
              </div>
              <EstadoSolicitudBadge estado={solicitudActiva.estado} />
            </div>

            <div className="px-6 py-4 grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Combustible</p>
                <p className="text-sm font-medium text-foreground">
                  {COMBUSTIBLES[solicitudActiva.tipo_combustible] ?? solicitudActiva.tipo_combustible}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Litros solicitados</p>
                <p className="text-sm font-medium text-foreground">{solicitudActiva.litros_solicitados} L</p>
              </div>
              {solicitudActiva.litros_aprobados && (
                <div>
                  <p className="text-xs text-muted-foreground mb-0.5">Litros aprobados</p>
                  <p className="text-sm font-medium text-primary">{solicitudActiva.litros_aprobados} L</p>
                </div>
              )}
              {solicitudActiva.fecha_expiracion && (
                <div>
                  <p className="text-xs text-muted-foreground mb-0.5">Válido hasta</p>
                  <p className="text-sm font-medium text-orange-600">
                    {formatFecha(solicitudActiva.fecha_expiracion, true)}
                  </p>
                </div>
              )}
              {solicitudActiva.observacion_anh && (
                <div className="col-span-2">
                  <p className="text-xs text-muted-foreground mb-1">Observación ANH</p>
                  <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
                    {solicitudActiva.observacion_anh}
                  </p>
                </div>
              )}
              {solicitudActiva.respuesta_consumidor && (
                <div className="col-span-2">
                  <p className="text-xs text-muted-foreground mb-1">Tu respuesta enviada</p>
                  <p className="text-sm text-state-success-fg bg-state-success-bg border border-state-success-fg/20 rounded-xl px-4 py-3">
                    {solicitudActiva.respuesta_consumidor}
                  </p>
                </div>
              )}
            </div>

            <div className="px-6 py-3 border-t border-border flex gap-2 flex-wrap">
              {solicitudActiva.estado === "APROBADA" && (
                <button onClick={descargarComprobante}
                  className="flex items-center gap-2 px-3 py-2 bg-primary text-primary-foreground rounded-lg text-xs font-medium hover:bg-primary-hover transition-colors">
                  <Download className="w-3.5 h-3.5" /> Descargar comprobante
                </button>
              )}
              <button onClick={() => descargarDeclaracion(solicitudActiva.id_publico)}
                className="flex items-center gap-2 px-3 py-2 bg-primary/10 text-primary rounded-lg text-xs font-medium hover:bg-primary/20 transition-colors">
                <FileText className="w-3.5 h-3.5" /> Declaración jurada
              </button>
              {["PENDIENTE", "OBSERVADA"].includes(solicitudActiva.estado) && (
                <button onClick={cancelar}
                  className="flex items-center gap-2 px-3 py-2 bg-red-50 text-red-600 rounded-lg text-xs font-medium hover:bg-red-100 transition-colors">
                  <X className="w-3.5 h-3.5" /> Cancelar solicitud
                </button>
              )}
            </div>
          </div>
        )}

        {/* FORMULARIO NUEVA SOLICITUD */}
        {mostrarForm && !solicitudActiva && (
          <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-border">
              <h2 className="font-semibold text-foreground">Nueva solicitud de combustible</h2>
            </div>
            <form onSubmit={handleSubmit(onSubmit)} className="px-6 py-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1.5">
                    Tipo de combustible *
                  </label>
                  <select {...register("tipo_combustible")} className={inputCls(!!errors.tipo_combustible)}>
                    <option value="">Seleccionar...</option>
                    {Object.entries(COMBUSTIBLES).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                  {errors.tipo_combustible && <p className="text-red-500 text-xs mt-1">{errors.tipo_combustible.message}</p>}
                </div>
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1.5">
                    Litros solicitados *
                  </label>
                  <input type="number" min={1} max={cupo?.disponible ?? 120}
                    {...register("litros_solicitados", { valueAsNumber: true })}
                    placeholder={`Máx. ${cupo?.disponible ?? 120} L disponibles`}
                    className={inputCls(!!errors.litros_solicitados)}
                  />
                  {errors.litros_solicitados && <p className="text-red-500 text-xs mt-1">{errors.litros_solicitados.message}</p>}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">
                  Uso / destino del combustible *
                </label>
                <textarea {...register("uso_combustible")} rows={3} maxLength={200}
                  placeholder="Describe para qué usarás el combustible..."
                  className={inputCls(!!errors.uso_combustible) + " resize-none"}
                />
                {errors.uso_combustible && <p className="text-red-500 text-xs mt-1">{errors.uso_combustible.message}</p>}
              </div>

              {/* UBICACIÓN ACTUAL */}
              <div className="border border-border rounded-xl p-4 space-y-4 bg-background/50">
                <p className="text-sm font-medium text-foreground">
                  ¿Dónde te encuentras actualmente? *
                </p>
                <p className="text-xs text-muted-foreground">
                  Indica tu ubicación actual (puede ser distinta a la registrada en tu perfil).
                  Esto permite mostrarte las estaciones de servicio cercanas.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Departamento *</label>
                    <select
                      value={watchDepto || 0}
                      onChange={e => onDeptoChange(Number(e.target.value))}
                      className={inputCls(!!errors.departamento)}
                    >
                      <option value={0}>Seleccionar...</option>
                      {deptos.map(d => <option key={d.id} value={d.id}>{d.nombre}</option>)}
                    </select>
                    {errors.departamento && <p className="text-red-500 text-xs mt-1">{errors.departamento.message}</p>}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Provincia *</label>
                    <select
                      value={watchProv || 0}
                      onChange={e => onProvChange(Number(e.target.value))}
                      disabled={!watchDepto || cargandoCatalogo}
                      className={inputCls(!!errors.provincia) + " disabled:opacity-50"}
                    >
                      <option value={0}>
                        {cargandoCatalogo ? "Cargando..." : "Seleccionar..."}
                      </option>
                      {provs.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                    </select>
                    {errors.provincia && <p className="text-red-500 text-xs mt-1">{errors.provincia.message}</p>}
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Municipio *</label>
                    <select
                      value={watchMuni || 0}
                      onChange={e => onMuniChange(Number(e.target.value))}
                      disabled={!watchProv || cargandoCatalogo}
                      className={inputCls(!!errors.municipio) + " disabled:opacity-50"}
                    >
                      <option value={0}>
                        {cargandoCatalogo ? "Cargando..." : "Seleccionar..."}
                      </option>
                      {munis.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}
                    </select>
                    {errors.municipio && <p className="text-red-500 text-xs mt-1">{errors.municipio.message}</p>}
                  </div>
                </div>

                {/* ESTACIÓN DE SERVICIO */}
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">
                    Estación de servicio *
                  </label>
                  <select
                    {...register("estacion_servicio", { valueAsNumber: true })}
                    disabled={!watchMuni || cargandoCatalogo}
                    className={inputCls(!!errors.estacion_servicio) + " disabled:opacity-50"}
                  >
                    <option value={0}>
                      {!watchMuni
                        ? "Selecciona primero el municipio"
                        : cargandoCatalogo
                          ? "Cargando..."
                          : estaciones.length === 0
                            ? "Sin estaciones activas en este municipio"
                            : "Seleccionar estación..."
                      }
                    </option>
                    {estaciones.map(e => <option key={e.id} value={e.id}>{e.nombre}</option>)}
                  </select>
                  {errors.estacion_servicio && <p className="text-red-500 text-xs mt-1">{errors.estacion_servicio.message}</p>}
                  <p className="text-xs text-muted-foreground mt-1">
                    La ANH confirmará la estación asignada al aprobar tu solicitud.
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">
                  Documento justificativo (opcional)
                </label>
                <label className={`flex items-center gap-3 w-full px-4 py-2.5 rounded-xl border text-sm cursor-pointer transition-colors ${
                  docJustificativo ? "border-primary bg-state-success-bg" : "border-border bg-input hover:bg-background"
                }`}>
                  <input type="file" accept="image/*,application/pdf" className="hidden"
                    onChange={e => setDocJustificativo(e.target.files?.[0] ?? null)} />
                  {docJustificativo
                    ? <><CheckCircle className="w-4 h-4 text-primary" /><span className="text-state-success-fg truncate">{docJustificativo.name}</span></>
                    : <><FileText className="w-4 h-4 text-muted-foreground" /><span className="text-muted-foreground">PDF, JPG o PNG — máx 10MB</span></>
                  }
                </label>
              </div>

              <div className="bg-background rounded-xl p-4 border border-border">
                <p className="text-xs text-muted-foreground leading-relaxed mb-3">
                  <strong>Declaración jurada:</strong> Declaro bajo juramento que los datos
                  proporcionados son verídicos y que el combustible solicitado será utilizado
                  exclusivamente para el uso declarado.
                </p>
                <label className="flex items-start gap-3 cursor-pointer">
                  <input type="checkbox" {...register("declaracion_jurada_confirmada")}
                    className="mt-0.5 w-4 h-4 rounded border-border text-primary accent-primary" />
                  <span className="text-sm text-foreground font-medium">
                    Confirmo y acepto la declaración jurada
                  </span>
                </label>
                {errors.declaracion_jurada_confirmada && (
                  <p className="text-red-500 text-xs mt-2">{errors.declaracion_jurada_confirmada.message}</p>
                )}
              </div>

              {sinCupo && (
                <div className="flex items-start gap-3 bg-state-danger-bg text-state-danger-fg rounded-xl px-4 py-3 text-sm">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>
                    Alcanzaste tu cupo mensual de {cupo?.total_mes} L. No puedes
                    crear nuevas solicitudes hasta el próximo mes.
                  </span>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => {
                    setMostrarForm(false); reset();
                    setProvs([]); setMunis([]); setEstaciones([]);
                  }}
                  className="px-4 py-2.5 border border-border text-muted-foreground rounded-xl text-sm hover:bg-background transition-colors">
                  Cancelar
                </button>
                <button type="submit" disabled={creando || sinCupo}
                  className="flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-primary-hover disabled:bg-slate-300 disabled:cursor-not-allowed text-primary-foreground rounded-xl text-sm font-medium transition-colors">
                  {creando
                    ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    : <FileText className="w-4 h-4" />
                  }
                  {creando ? "Enviando..." : "Enviar solicitud"}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* HISTORIAL */}
        {historial.length > 0 && (
          <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
            <button onClick={() => setMostrarHistorial(!mostrarHistorial)}
              className="w-full px-6 py-4 flex items-center justify-between hover:bg-background transition-colors">
              <div className="flex items-center gap-3">
                <Clock className="w-5 h-5 text-muted-foreground" />
                <span className="font-semibold text-foreground">Historial ({historial.length})</span>
              </div>
              {mostrarHistorial ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </button>
            {mostrarHistorial && (
              <div className="border-t border-border divide-y divide-border">
                {historial.map(s => (
                  <div key={s.id_publico} className="px-6 py-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        #{formatIdPublico(s.id_publico)} — {COMBUSTIBLES[s.tipo_combustible]} {s.litros_solicitados}L
                      </p>
                      <p className="text-xs text-muted-foreground">{formatFecha(s.fecha_creacion)}</p>
                    </div>
                    <EstadoSolicitudBadge estado={s.estado} />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ESTADO VACÍO */}
        {!solicitudActiva && !mostrarForm && historial.length === 0 && (
          <div className="bg-card rounded-2xl border border-border shadow-sm px-6 py-12 text-center">
            <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-4">
              <FileText className="w-8 h-8 text-primary" />
            </div>
            <h3 className="text-foreground font-semibold mb-2">Sin solicitudes</h3>
            <p className="text-muted-foreground text-sm mb-6">
              No tienes solicitudes registradas. Crea tu primera solicitud de combustible.
            </p>
            <button onClick={() => setMostrarForm(true)}
              className="flex items-center gap-2 mx-auto px-5 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary-hover transition-colors">
              <Plus className="w-4 h-4" /> Nueva solicitud
            </button>
          </div>
        )}
      </div>

      {/* PDF VIEWER */}
      {pdfViewer === "declaracion" && solicitudActiva && (
        <PDFViewer
          titulo={"Declaración Jurada"}
          onClose={() => setPdfViewer(null)}
          fetchPDF={() => solicitudesService.getDeclaracionJuradaBlob(solicitudActiva.id_publico)}
          onDescargar={() => descargarDeclaracion(solicitudActiva.id_publico)}
        />
      )}
      {pdfViewer === "comprobante" && solicitudActiva && (
        <PDFViewer
          titulo={"Comprobante de Aprobación"}
          onClose={() => setPdfViewer(null)}
          fetchPDF={() => solicitudesService.getComprobanteBlob(solicitudActiva.id_publico)}
          onDescargar={descargarComprobante}
        />
      )}

    </Layout>
  );
}