// src/pages/anh/DetalleSolicitud.tsx

import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import Layout from "../../components/Layout";
import { EstadoSolicitudBadge } from "../../components/ui/EstadoBadge";
import { solicitudesService } from "../../services/solicitudes.service";
import { estacionesService } from "../../services/estaciones.service";
import { catalogosService } from "../../services/catalogos.service";
import type { Solicitud, CupoConsumidor } from "../../types/solicitud.types";
import { COMBUSTIBLES } from "../../utils/constants";
import { formatFecha, formatIdPublico } from "../../utils/format";
import {
  ArrowLeft, CheckCircle, Eye, AlertCircle,
  AlertTriangle, MessageSquare, XCircle, FileText
} from "lucide-react";
import PDFViewer from "../../components/ui/PDFViewer";

// ------------------------------------------------
// SCHEMAS
// ------------------------------------------------

const aprobarSchema = z.object({
  tipo_combustible_aprobado: z.string().min(1, "Selecciona el tipo de combustible"),
  litros_aprobados:          z.number().int().min(1, "Mínimo 1 litro").max(120, "Máximo 120 L"),
  departamento:              z.number().int().positive("Selecciona el departamento"),
  provincia:                 z.number().int().positive("Selecciona la provincia"),
  municipio:                 z.number().int().positive("Selecciona el municipio"),
  estacion_servicio:         z.number().int().positive("Selecciona una estación"),
  observacion_anh:           z.string().optional(),
});

const observarSchema = z.object({
  observacion_anh: z.string().min(10, "Mínimo 10 caracteres"),
});

const rechazarSchema = z.object({
  observacion_anh: z.string().min(10, "Mínimo 10 caracteres"),
});

type AprobarData = z.infer<typeof aprobarSchema>;
type ObservarData = z.infer<typeof observarSchema>;
type RechazarData = z.infer<typeof rechazarSchema>;

interface Opcion { id: number; nombre: string; }

// ------------------------------------------------
// HELPER
// ------------------------------------------------

function Dato({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground mb-0.5">{label}</p>
      <p className="text-sm font-medium text-foreground">{value ?? "—"}</p>
    </div>
  );
}

// ------------------------------------------------
// COMPONENTE
// ------------------------------------------------

export default function DetalleSolicitudANH() {
  const { idPublico } = useParams<{ idPublico: string }>();
  const navigate      = useNavigate();

  const [solicitud,   setSolicitud]   = useState<Solicitud | null>(null);
  const [loading,     setLoading]     = useState(true);
  const [accion,      setAccion]      = useState<"aprobar" | "observar" | "rechazar" | null>(null);
  const [procesando,  setProcesando]  = useState(false);
  const [error,       setError]       = useState("");
  const [exito,       setExito]       = useState("");
  const [pdfViewer,   setPdfViewer]   = useState<"declaracion" | "comprobante" | null>(null);

  const [deptos,     setDeptos]     = useState<Opcion[]>([]);
  const [provs,      setProvs]      = useState<Opcion[]>([]);
  const [munis,      setMunis]      = useState<Opcion[]>([]);
  const [estaciones, setEstaciones] = useState<Opcion[]>([]);
  const [cargandoCatalogo, setCargandoCatalogo] = useState(false);
  const [cupoConsumidor, setCupoConsumidor] = useState<CupoConsumidor | null>(null);

  const formAprobar = useForm<AprobarData>({
    resolver: zodResolver(aprobarSchema),
    defaultValues: {
      tipo_combustible_aprobado: "",
      litros_aprobados:          1,
      departamento:              0,
      provincia:                 0,
      municipio:                 0,
      estacion_servicio:         0,
      observacion_anh:           "",
    }
  });

  const formObservar = useForm<ObservarData>({ resolver: zodResolver(observarSchema) });
  const formRechazar = useForm<RechazarData>({ resolver: zodResolver(rechazarSchema) });

  const watchCombustible = formAprobar.watch("tipo_combustible_aprobado");
  const watchLitros      = formAprobar.watch("litros_aprobados");
  const watchDepto       = formAprobar.watch("departamento");
  const watchProv        = formAprobar.watch("provincia");
  const watchMuni        = formAprobar.watch("municipio");

  useEffect(() => {
    if (!idPublico) return;
    Promise.all([
      solicitudesService.getById(idPublico),
      catalogosService.getDepartamentos(),
    ]).then(([s, deps]) => {
      setSolicitud(s);
      setDeptos(deps);
    }).catch(() => setError("Error al cargar la solicitud."))
      .finally(() => setLoading(false));
  }, [idPublico]);

  useEffect(() => {
    if (accion !== "aprobar" || !solicitud) return;

    setCupoConsumidor(null);
    solicitudesService.obtenerCupoConsumidor(solicitud.consumidor.id)
      .then(setCupoConsumidor)
      .catch(() => {}); // el form igual funciona sin el dato, solo no muestra el cupo

    formAprobar.reset({
      tipo_combustible_aprobado: solicitud.tipo_combustible,
      litros_aprobados:          solicitud.litros_solicitados,
      departamento:              solicitud.departamento ?? 0,
      provincia:                 solicitud.provincia    ?? 0,
      municipio:                 solicitud.municipio    ?? 0,
      estacion_servicio:         solicitud.estacion_servicio ?? 0,
      observacion_anh:           "",
    });

    const cargarCascada = async () => {
      if (!solicitud.departamento) return;
      setCargandoCatalogo(true);
      try {
        const [provincias, municipios] = await Promise.all([
          catalogosService.getProvincias(solicitud.departamento),
          solicitud.provincia ? catalogosService.getMunicipios(solicitud.provincia) : Promise.resolve([]),
        ]);
        setProvs(provincias);
        setMunis(municipios);

        if (solicitud.municipio) {
          const data = await estacionesService.getAll({
            municipio: String(solicitud.municipio),
            estado: "ACTIVA",
          });
          const lista = Array.isArray(data) ? data : (data as any).results ?? [];
          setEstaciones(lista.map((e: any) => ({ id: e.id, nombre: e.nombre })));
        }
      } finally {
        setCargandoCatalogo(false);
      }
    };

    cargarCascada();
  }, [accion, solicitud]);

  const onDeptoChange = async (deptoId: number) => {
    formAprobar.setValue("departamento", deptoId);
    formAprobar.setValue("provincia", 0);
    formAprobar.setValue("municipio", 0);
    formAprobar.setValue("estacion_servicio", 0);
    setProvs([]); setMunis([]); setEstaciones([]);
    if (!deptoId) return;
    setCargandoCatalogo(true);
    try {
      const data = await catalogosService.getProvincias(deptoId);
      setProvs(data);
    } finally { setCargandoCatalogo(false); }
  };

  const onProvChange = async (provId: number) => {
    formAprobar.setValue("provincia", provId);
    formAprobar.setValue("municipio", 0);
    formAprobar.setValue("estacion_servicio", 0);
    setMunis([]); setEstaciones([]);
    if (!provId) return;
    setCargandoCatalogo(true);
    try {
      const data = await catalogosService.getMunicipios(provId);
      setMunis(data);
    } finally { setCargandoCatalogo(false); }
  };

  const onMuniChange = async (muniId: number) => {
    formAprobar.setValue("municipio", muniId);
    formAprobar.setValue("estacion_servicio", 0);
    setEstaciones([]);
    if (!muniId) return;
    setCargandoCatalogo(true);
    try {
      const data = await estacionesService.getAll({ municipio: String(muniId), estado: "ACTIVA" });
      const lista = Array.isArray(data) ? data : (data as any).results ?? [];
      setEstaciones(lista.map((e: any) => ({ id: e.id, nombre: e.nombre })));
    } finally { setCargandoCatalogo(false); }
  };

  const onAprobar = async (data: AprobarData) => {
    if (!idPublico) return;
    setProcesando(true); setError("");
    try {
      const s = await solicitudesService.aprobar(idPublico, {
        tipo_combustible_aprobado: data.tipo_combustible_aprobado,
        litros_aprobados:          data.litros_aprobados,
        estacion_servicio:         data.estacion_servicio,
        observacion_anh:           data.observacion_anh,
      });
      setSolicitud(s);
      setAccion(null);
      setExito("Solicitud aprobada exitosamente.");
    } catch (err: unknown) {
      const e = err as { response?: { data?: Record<string, unknown> } };
      const data2 = e.response?.data;
      if (data2) {
        const msgs = Object.entries(data2)
          .map(([, v]) => Array.isArray(v) ? v[0] : String(v))
          .join(" | ");
        setError(msgs);
      } else {
        setError("Error al aprobar la solicitud.");
      }
      // Resincronizar: el 400 puede ser justo por cupo excedido, y el
      // número mostrado en pantalla ya no sería el real.
      if (solicitud) {
        solicitudesService.obtenerCupoConsumidor(solicitud.consumidor.id)
          .then(setCupoConsumidor)
          .catch(() => {});
      }
    } finally { setProcesando(false); }
  };

  const onObservar = async (data: ObservarData) => {
    if (!idPublico) return;
    setProcesando(true); setError("");
    try {
      const s = await solicitudesService.observar(idPublico, data.observacion_anh);
      setSolicitud(s);
      setAccion(null);
      setExito("Solicitud observada. El consumidor será notificado.");
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail ?? "Error al observar la solicitud.");
    } finally { setProcesando(false); }
  };

  const onRechazar = async (data: RechazarData) => {
    if (!idPublico) return;
    setProcesando(true); setError("");
    try {
      const s = await solicitudesService.rechazar(idPublico, data.observacion_anh);
      setSolicitud(s);
      setAccion(null);
      setExito("Solicitud rechazada. El consumidor será notificado.");
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail ?? "Error al rechazar la solicitud.");
    } finally { setProcesando(false); }
  };

  const inputCls  = "w-full px-4 py-2.5 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none";
  const selectCls = "w-full px-4 py-2.5 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none disabled:opacity-50";

  if (loading) return (
    <Layout>
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    </Layout>
  );

  if (!solicitud) return (
    <Layout>
      <div className="text-center py-16">
        <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-3" />
        <p className="text-muted-foreground">{error || "Solicitud no encontrada."}</p>
      </div>
    </Layout>
  );

  const puedeAprobar  = ["PENDIENTE", "OBSERVADA"].includes(solicitud.estado);
  const puedeObservar = solicitud.estado === "PENDIENTE";
  const puedeRechazar = ["PENDIENTE", "OBSERVADA"].includes(solicitud.estado);

  const combustibleModificado = accion === "aprobar" &&
    watchCombustible &&
    watchCombustible !== solicitud.tipo_combustible;

  const litrosModificados = accion === "aprobar" &&
    watchLitros > 0 &&
    watchLitros !== solicitud.litros_solicitados;

  return (
    <Layout>
      <div className="max-w-3xl mx-auto space-y-5">

        {/* HEADER */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/anh/solicitudes")}
            className="p-2 rounded-xl border border-border text-muted-foreground hover:bg-card transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-bold text-foreground">
                Solicitud #{formatIdPublico(solicitud.id_publico)}
              </h1>
              <EstadoSolicitudBadge estado={solicitud.estado} />
            </div>
            <p className="text-muted-foreground text-sm">{formatFecha(solicitud.fecha_creacion, true)}</p>
          </div>
        </div>

        {/* ALERTAS */}
        {error && (
          <div className="flex items-center gap-3 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}
        {exito && (
          <div className="flex items-center gap-3 bg-state-success-bg border border-state-success-fg/20 text-state-success-fg rounded-xl px-4 py-3 text-sm">
            <CheckCircle className="w-4 h-4 shrink-0" /> {exito}
          </div>
        )}

        {/* DATOS CONSUMIDOR */}
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-border">
            <h2 className="font-semibold text-foreground">Datos del solicitante</h2>
          </div>
          <div className="px-6 py-4 grid grid-cols-2 gap-4">
            <Dato label="Nombre completo" value={solicitud.consumidor?.nombre_completo} />
            <Dato label="Email"           value={solicitud.consumidor?.email} />
          </div>
        </div>

        {/* DATOS SOLICITUD */}
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-border">
            <h2 className="font-semibold text-foreground">Datos de la solicitud</h2>
          </div>
          <div className="px-6 py-4 grid grid-cols-2 gap-4">
            <Dato label="Tipo combustible"    value={COMBUSTIBLES[solicitud.tipo_combustible] ?? solicitud.tipo_combustible} />
            <Dato label="Litros solicitados"  value={`${solicitud.litros_solicitados} L`} />
            <Dato label="Uso / destino"       value={solicitud.uso_combustible} />
            <Dato label="Fecha solicitud"     value={formatFecha(solicitud.fecha_creacion, true)} />
            <Dato label="Departamento"        value={(solicitud as any).departamento_nombre ?? "—"} />
            <Dato label="Municipio"           value={(solicitud as any).municipio_nombre ?? "—"} />
            <Dato label="Estación preferida"  value={(solicitud as any).estacion_nombre ?? "Sin preferencia"} />
            {solicitud.observacion_anh && (
              <div className="col-span-2">
                <p className="text-xs text-muted-foreground mb-1">Observación ANH</p>
                <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-4 py-2">
                  {solicitud.observacion_anh}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* DATOS APROBACIÓN */}
        {solicitud.litros_aprobados && (
          <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-border">
              <h2 className="font-semibold text-foreground">Datos de aprobación</h2>
            </div>
            <div className="px-6 py-4 grid grid-cols-2 gap-4">
              <Dato label="Combustible aprobado" value={COMBUSTIBLES[solicitud.tipo_combustible_aprobado ?? ""] ?? solicitud.tipo_combustible_aprobado} />
              <Dato label="Litros aprobados"     value={`${solicitud.litros_aprobados} L`} />
              <Dato label="Fecha aprobación"     value={formatFecha(solicitud.fecha_aprobacion, true)} />
              <Dato label="Válido hasta"         value={formatFecha(solicitud.fecha_expiracion, true)} />
              {solicitud.litros_despachados && (
                <Dato label="Litros despachados" value={`${solicitud.litros_despachados} L`} />
              )}
              {solicitud.observacion_despacho && (
                <div className="col-span-2">
                  <p className="text-xs text-muted-foreground mb-1">Observación de despacho</p>
                  <p className="text-sm text-foreground bg-background border border-border rounded-xl px-4 py-2">
                    {solicitud.observacion_despacho}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ACCIONES */}
        {(puedeAprobar || puedeObservar || puedeRechazar) && (
          <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-border">
              <h2 className="font-semibold text-foreground">Acciones</h2>
            </div>
            <div className="px-6 py-4">

              {/* BOTONES */}
              {!accion && (
                <div className="flex gap-3 flex-wrap">
                  {puedeAprobar && (
                    <button onClick={() => setAccion("aprobar")} className="flex items-center gap-2 px-4 py-2.5 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-700 transition-colors">
                      <CheckCircle className="w-4 h-4" /> Aprobar
                    </button>
                  )}
                  {puedeObservar && (
                    <button onClick={() => setAccion("observar")} className="flex items-center gap-2 px-4 py-2.5 bg-amber-500 text-white rounded-xl text-sm font-medium hover:bg-amber-600 transition-colors">
                      <MessageSquare className="w-4 h-4" /> Observar
                    </button>
                  )}
                  {puedeRechazar && (
                    <button onClick={() => setAccion("rechazar")} className="flex items-center gap-2 px-4 py-2.5 bg-red-600 text-white rounded-xl text-sm font-medium hover:bg-red-700 transition-colors">
                      <XCircle className="w-4 h-4" /> Rechazar
                    </button>
                  )}
                </div>
              )}

              {/* FORM APROBAR */}
              {accion === "aprobar" && (
                <form onSubmit={formAprobar.handleSubmit(onAprobar)} className="space-y-4">
                  <h3 className="font-medium text-green-700 text-sm">Aprobar solicitud</h3>

                  {/* Referencia de lo solicitado */}
                  <div className="bg-primary/10 border border-primary/20 rounded-xl px-4 py-3 text-xs text-primary flex gap-6 flex-wrap">
                    <span>Solicitó: <strong>{COMBUSTIBLES[solicitud.tipo_combustible] ?? solicitud.tipo_combustible}</strong></span>
                    <span>Litros: <strong>{solicitud.litros_solicitados} L</strong></span>
                    <span>Estación preferida: <strong>{(solicitud as any).estacion_nombre ?? "Sin preferencia"}</strong></span>
                  </div>

                  {/* Cupo mensual del consumidor */}
                  {cupoConsumidor && (
                    <div className="bg-background border border-border rounded-xl px-4 py-3 text-xs text-foreground">
                      Cupo del consumidor: <strong>{cupoConsumidor.usado}/{cupoConsumidor.total_mes} L</strong> este mes.
                      Máximo aprobable: <strong>{cupoConsumidor.disponible}L</strong>.
                    </div>
                  )}

                  {/* Advertencias */}
                  {combustibleModificado && (
                    <div className="flex items-start gap-2 bg-amber-50 border border-amber-300 text-amber-700 rounded-xl px-4 py-3 text-xs">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>Estás modificando el tipo de combustible: el consumidor solicitó <strong>{COMBUSTIBLES[solicitud.tipo_combustible]}</strong> y estás aprobando <strong>{COMBUSTIBLES[watchCombustible] ?? watchCombustible}</strong>.</span>
                    </div>
                  )}
                  {litrosModificados && (
                    <div className="flex items-start gap-2 bg-amber-50 border border-amber-300 text-amber-700 rounded-xl px-4 py-3 text-xs">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>Estás modificando los litros: el consumidor solicitó <strong>{solicitud.litros_solicitados} L</strong> y estás aprobando <strong>{watchLitros} L</strong>.</span>
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-muted-foreground mb-1">Combustible a aprobar *</label>
                      <select {...formAprobar.register("tipo_combustible_aprobado")} className={selectCls}>
                        <option value="">Seleccionar...</option>
                        {Object.entries(COMBUSTIBLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                      {formAprobar.formState.errors.tipo_combustible_aprobado && <p className="text-red-500 text-xs mt-1">{formAprobar.formState.errors.tipo_combustible_aprobado.message}</p>}
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-muted-foreground mb-1">Litros aprobados *</label>
                      <input type="number" min={1}
                        max={cupoConsumidor ? Math.min(solicitud.litros_solicitados, cupoConsumidor.disponible) : solicitud.litros_solicitados}
                        {...formAprobar.register("litros_aprobados", { valueAsNumber: true })} className={inputCls} />
                      {formAprobar.formState.errors.litros_aprobados && <p className="text-red-500 text-xs mt-1">{formAprobar.formState.errors.litros_aprobados.message}</p>}
                    </div>
                  </div>

                  {/* CASCADA GEOGRÁFICA */}
                  <div className="border border-border rounded-xl p-4 space-y-3 bg-background/50">
                    <p className="text-xs font-medium text-foreground">
                      Estación de servicio a asignar *
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Precargado con la ubicación indicada por el consumidor. Puedes cambiarlo si es necesario.
                    </p>

                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-1">Departamento *</label>
                        <select
                          value={watchDepto || 0}
                          onChange={e => onDeptoChange(Number(e.target.value))}
                          className={selectCls}
                        >
                          <option value={0}>Seleccionar...</option>
                          {deptos.map(d => <option key={d.id} value={d.id}>{d.nombre}</option>)}
                        </select>
                        {formAprobar.formState.errors.departamento && <p className="text-red-500 text-xs mt-1">{formAprobar.formState.errors.departamento.message}</p>}
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-1">Provincia *</label>
                        <select
                          value={watchProv || 0}
                          onChange={e => onProvChange(Number(e.target.value))}
                          disabled={!watchDepto || cargandoCatalogo}
                          className={selectCls}
                        >
                          <option value={0}>{cargandoCatalogo ? "Cargando..." : "Seleccionar..."}</option>
                          {provs.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                        </select>
                        {formAprobar.formState.errors.provincia && <p className="text-red-500 text-xs mt-1">{formAprobar.formState.errors.provincia.message}</p>}
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-1">Municipio *</label>
                        <select
                          value={watchMuni || 0}
                          onChange={e => onMuniChange(Number(e.target.value))}
                          disabled={!watchProv || cargandoCatalogo}
                          className={selectCls}
                        >
                          <option value={0}>{cargandoCatalogo ? "Cargando..." : "Seleccionar..."}</option>
                          {munis.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}
                        </select>
                        {formAprobar.formState.errors.municipio && <p className="text-red-500 text-xs mt-1">{formAprobar.formState.errors.municipio.message}</p>}
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-muted-foreground mb-1">Estación *</label>
                      <select
                        {...formAprobar.register("estacion_servicio", { valueAsNumber: true })}
                        disabled={!watchMuni || cargandoCatalogo}
                        className={selectCls}
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
                      {formAprobar.formState.errors.estacion_servicio && <p className="text-red-500 text-xs mt-1">{formAprobar.formState.errors.estacion_servicio.message}</p>}
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Observación (opcional)</label>
                    <textarea {...formAprobar.register("observacion_anh")} rows={2} className={inputCls + " resize-none"} placeholder="Notas para el consumidor..." />
                  </div>

                  <div className="flex gap-3">
                    <button type="button" onClick={() => { setAccion(null); setProvs([]); setMunis([]); setEstaciones([]); }} className="px-4 py-2 border border-border text-muted-foreground rounded-xl text-sm hover:bg-background transition-colors">Cancelar</button>
                    <button type="submit" disabled={procesando} className="flex items-center gap-2 px-5 py-2 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-700 disabled:bg-slate-300 transition-colors">
                      {procesando ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                      Confirmar aprobación
                    </button>
                  </div>
                </form>
              )}

              {/* FORM OBSERVAR */}
              {accion === "observar" && (
                <form onSubmit={formObservar.handleSubmit(onObservar)} className="space-y-4">
                  <h3 className="font-medium text-amber-700 text-sm">Observar solicitud</h3>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Motivo de la observación *</label>
                    <textarea {...formObservar.register("observacion_anh")} rows={3} className={inputCls + " resize-none"} placeholder="Describe qué debe corregir o justificar el consumidor..." />
                    {formObservar.formState.errors.observacion_anh && <p className="text-red-500 text-xs mt-1">{formObservar.formState.errors.observacion_anh.message}</p>}
                  </div>
                  <div className="flex gap-3">
                    <button type="button" onClick={() => setAccion(null)} className="px-4 py-2 border border-border text-muted-foreground rounded-xl text-sm hover:bg-background transition-colors">Cancelar</button>
                    <button type="submit" disabled={procesando} className="flex items-center gap-2 px-5 py-2 bg-amber-500 text-white rounded-xl text-sm font-medium hover:bg-amber-600 disabled:bg-slate-300 transition-colors">
                      {procesando ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <MessageSquare className="w-4 h-4" />}
                      Enviar observación
                    </button>
                  </div>
                </form>
              )}

              {/* FORM RECHAZAR */}
              {accion === "rechazar" && (
                <form onSubmit={formRechazar.handleSubmit(onRechazar)} className="space-y-4">
                  <h3 className="font-medium text-red-700 text-sm">Rechazar solicitud</h3>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Motivo del rechazo *</label>
                    <textarea {...formRechazar.register("observacion_anh")} rows={3} className={inputCls + " resize-none"} placeholder="Describe el motivo del rechazo..." />
                    {formRechazar.formState.errors.observacion_anh && <p className="text-red-500 text-xs mt-1">{formRechazar.formState.errors.observacion_anh.message}</p>}
                  </div>
                  <div className="flex gap-3">
                    <button type="button" onClick={() => setAccion(null)} className="px-4 py-2 border border-border text-muted-foreground rounded-xl text-sm hover:bg-background transition-colors">Cancelar</button>
                    <button type="submit" disabled={procesando} className="flex items-center gap-2 px-5 py-2 bg-red-600 text-white rounded-xl text-sm font-medium hover:bg-red-700 disabled:bg-slate-300 transition-colors">
                      {procesando ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> : <XCircle className="w-4 h-4" />}
                      Confirmar rechazo
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        )}

        {/* DOCUMENTOS */}
        <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-border">
            <h2 className="font-semibold text-foreground">Documentos</h2>
          </div>
          <div className="px-6 py-4 flex gap-3 flex-wrap">
            <button
              onClick={() => setPdfViewer("declaracion")}
              className="flex items-center gap-2 px-4 py-2.5 bg-primary/10 text-primary rounded-xl text-sm font-medium hover:bg-primary/20 transition-colors"
            >
              <Eye className="w-4 h-4" /> Ver declaración jurada
            </button>
            {solicitud.estado === "APROBADA" && (
              <button
                onClick={() => setPdfViewer("comprobante")}
                className="flex items-center gap-2 px-4 py-2.5 bg-state-success-bg text-state-success-fg rounded-xl text-sm font-medium hover:opacity-90 transition-opacity"
              >
                <Eye className="w-4 h-4" /> Ver comprobante
              </button>
            )}
            {solicitud.documento_justificativo &&(
              <a
                href={solicitud.documento_justificativo}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-2 px-4 py-2.5 bg-background text-foreground rounded-xl text-sm font-medium hover:bg-border transition-colors"
              >
                <FileText className="w-4 h-4" /> Doc. justificativo
              </a>
            )}
          </div>
        </div>

      </div>

      {/* PDF VIEWER MODAL */}
      {pdfViewer === "declaracion" && (
        <PDFViewer
          titulo={"Declaración Jurada — #" + formatIdPublico(solicitud.id_publico)}
          onClose={() => setPdfViewer(null)}
          fetchPDF={() => solicitudesService.getDeclaracionJuradaBlob(solicitud.id_publico)}
          onDescargar={() => solicitudesService.descargarDeclaracionJurada(solicitud.id_publico)}
        />
      )}
      {pdfViewer === "comprobante" && (
        <PDFViewer
          titulo={"Comprobante — #" + formatIdPublico(solicitud.id_publico)}
          onClose={() => setPdfViewer(null)}
          fetchPDF={() => solicitudesService.getComprobanteBlob(solicitud.id_publico)}
          onDescargar={() => solicitudesService.descargarComprobante(solicitud.id_publico)}
        />
      )}

    </Layout>
  );
}