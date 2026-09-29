// src/pages/anh/Reportes.tsx

import { useState, useEffect, useCallback, useRef } from "react";
import type { ReactNode } from "react";
import Layout from "../../components/Layout";
import { estacionesService } from "../../services/estaciones.service";
import { reportesService } from "../../services/reportes.service";
import { Card, CardHeader, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { Spinner } from "../../components/ui/Spinner";
import { ESTADOS_SOLICITUD, ESTADOS_SOLICITUD_HEX } from "../../utils/constants";
import { fechaLocalISO } from "../../utils/format";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  PieChart, Pie, Cell, ResponsiveContainer, LabelList,
} from "recharts";
import {
  BarChart3, FileText, FileSpreadsheet, Filter, CalendarRange,
} from "lucide-react";

// ------------------------------------------------
// CONSTANTES
// ------------------------------------------------

const FILTROS_CONSUMIDORES = [
  { value: "TODOS",        label: "Todos los consumidores" },
  { value: "CUPO_AGOTADO", label: "Cupo mensual agotado" },
  { value: "BLOQUEADOS",   label: "Consumidores bloqueados" },
  { value: "EN_REVISION",  label: "Consumidores en revisión" },
];

const ESTADOS_OPTIONS = [
  { value: "", label: "Todos los estados" },
  ...Object.entries(ESTADOS_SOLICITUD).map(([value, { label }]) => ({ value, label })),
];

// Tiempo que un mensaje de alerta permanece visible antes de auto-ocultarse
const ALERT_TIMEOUT = 4000;

const SIN_DATOS = "No hay solicitudes en el rango seleccionado.";

// Mismo color de "creadas" que el navbar (token navbar)
const COLOR_CREADAS = "#17212B";

interface Estadisticas {
  periodo: { desde: string; hasta: string; texto: string };
  total: number;
  litros_despachados: number;
  aprobadas_alguna_vez: number;
  rechazadas: number;
  resueltas: number;
  tasa_aprobacion: number | null;
  tasa_rechazo: number | null;
  por_estado: { estado: string; total: number }[];
  evolucion: {
    agrupacion: "dia" | "mes";
    puntos: { etiqueta: string; creadas: number; aprobadas: number; despachadas: number }[];
  };
  despachados_por_combustible: { tipo: string; etiqueta: string; litros: number }[];
  por_estacion:  { estacion_id: number; nombre: string; litros_despachados: number; despachos: number }[];
  por_municipio: { municipio: string; litros_despachados: number }[];
}

// Primer día del mes actual / hoy / mes actual, en fecha LOCAL.
const primerDiaDelMes = () => {
  const hoy = new Date();
  return fechaLocalISO(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
};
const mesActual = () => fechaLocalISO().slice(0, 7);

const formatLitros = (v: number) => `${v.toLocaleString("es-BO")} L`;
const formatTasa = (v: number | null) => (v === null ? "—" : `${v.toLocaleString("es-BO")} %`);

// Con responseType "blob", el cuerpo de un 400 también llega como Blob:
// se lee para mostrar el mensaje del backend en vez de uno genérico.
async function mensajeDeError(err: unknown, porDefecto: string): Promise<string> {
  const data = (err as { response?: { data?: unknown } }).response?.data;
  try {
    if (data instanceof Blob) {
      const json = JSON.parse(await data.text());
      if (typeof json.detail === "string") return json.detail;
    }
  } catch { /* cuerpo no JSON: mensaje por defecto */ }
  return porDefecto;
}

// ------------------------------------------------
// COMPONENTES DE PRESENTACIÓN
// ------------------------------------------------

function Metrica({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <CardBody className="px-5 py-4">
        <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">{label}</p>
        <p className="text-2xl font-bold text-foreground">{value}</p>
      </CardBody>
    </Card>
  );
}

function Grafico({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader><h3 className="font-semibold text-foreground text-sm">{titulo}</h3></CardHeader>
      <CardBody>{children}</CardBody>
    </Card>
  );
}

// Tooltip con el mismo lenguaje visual que el resto de las tarjetas,
// en vez del tooltip blanco por defecto de Recharts.
const tooltipStyle = {
  contentStyle: {
    backgroundColor: "var(--card)",
    border: "1px solid var(--border)",
    borderRadius: "0.75rem",
    fontSize: "12px",
  },
};

// ------------------------------------------------
// PÁGINA
// ------------------------------------------------

export default function ReportesANH() {
  const [tab, setTab] = useState<"solicitudes" | "consumidores">("solicitudes");

  // Por defecto: el mes actual (del 1° a hoy)
  const [fechaDesde,        setFechaDesde]        = useState(primerDiaDelMes);
  const [fechaHasta,        setFechaHasta]        = useState(() => fechaLocalISO());
  const [estadoFiltro,      setEstadoFiltro]      = useState("");
  const [combustibleFiltro, setCombustibleFiltro] = useState("");
  const [estacionFiltro,    setEstacionFiltro]    = useState("");
  const [estaciones,        setEstaciones]        = useState<{ id: number; nombre: string }[]>([]);

  const [stats,     setStats]     = useState<Estadisticas | null>(null);
  const [loadStats, setLoadStats] = useState(false);

  // Validación del rango en el cliente: no se piden datos con desde > hasta
  const rangoInvalido = !!fechaDesde && !!fechaHasta && fechaDesde > fechaHasta;
  const sinDatos      = !!stats && stats.total === 0;

  // Alertas separadas por tab para que un mensaje de "Solicitudes"
  // no quede visible al cambiar a la pestaña "Consumidores" (y viceversa).
  const [alertaSol,  setAlertaSol]  = useState<{ type: "error" | "success"; message: string } | null>(null);
  const [alertaCons, setAlertaCons] = useState<{ type: "error" | "success"; message: string } | null>(null);
  const timerSolRef  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const timerConsRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flashSol = (type: "error" | "success", message: string) => {
    setAlertaSol({ type, message });
    if (timerSolRef.current) clearTimeout(timerSolRef.current);
    timerSolRef.current = setTimeout(() => setAlertaSol(null), ALERT_TIMEOUT);
  };
  const flashCons = (type: "error" | "success", message: string) => {
    setAlertaCons({ type, message });
    if (timerConsRef.current) clearTimeout(timerConsRef.current);
    timerConsRef.current = setTimeout(() => setAlertaCons(null), ALERT_TIMEOUT);
  };

  // Formato que se está descargando en cada tab (para mostrar loading
  // solo en el botón correspondiente, no en los dos a la vez)
  const [descargandoSol,  setDescargandoSol]  = useState<"PDF" | "EXCEL" | null>(null);
  const [descargandoCons, setDescargandoCons] = useState<"PDF" | "EXCEL" | null>(null);

  const [filtroConsumidor, setFiltroConsumidor] = useState("TODOS");
  const [mesCons,          setMesCons]          = useState(mesActual);
  const [incluirDetalle,   setIncluirDetalle]   = useState(false);

  useEffect(() => {
    estacionesService.getAll({ estado: "ACTIVA" }).then(data => {
      const lista = Array.isArray(data) ? data : (data as any).results ?? [];
      setEstaciones(lista.map((e: any) => ({ id: e.id, nombre: e.nombre })));
    }).catch(() => flashSol("error", "No se pudieron cargar las estaciones del filtro."));
  }, []);

  const filtrosSolicitudes = useCallback(() => {
    const params: Record<string, string> = {};
    if (fechaDesde)        params.fecha_desde = fechaDesde;
    if (fechaHasta)        params.fecha_hasta = fechaHasta;
    if (estadoFiltro)      params.estado      = estadoFiltro;
    if (combustibleFiltro) params.combustible = combustibleFiltro;
    if (estacionFiltro)    params.estacion    = estacionFiltro;
    return params;
  }, [fechaDesde, fechaHasta, estadoFiltro, combustibleFiltro, estacionFiltro]);

  const cargarEstadisticas = useCallback(async () => {
    setLoadStats(true);
    try {
      setStats(await reportesService.getEstadisticas(filtrosSolicitudes()));
    } catch {
      setStats(null);
      flashSol("error", "No se pudieron cargar las estadísticas.");
    } finally {
      setLoadStats(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtrosSolicitudes]);

  // Los filtros se aplican automáticamente al cambiar cualquiera de ellos.
  // Con el rango inválido no se consulta (se muestra el aviso).
  useEffect(() => {
    if (tab === "solicitudes" && !rangoInvalido) cargarEstadisticas();
  }, [tab, rangoInvalido, cargarEstadisticas]);

  const descargarSolicitudes = async (destFormato: "PDF" | "EXCEL") => {
    setDescargandoSol(destFormato);
    try {
      await reportesService.descargarSolicitudes(filtrosSolicitudes(), destFormato);
      flashSol("success", `Reporte ${destFormato} descargado correctamente.`);
    } catch (err) {
      flashSol("error", await mensajeDeError(err, "Ocurrió un error al generar el reporte."));
    } finally {
      setDescargandoSol(null);
    }
  };

  const descargarConsumidores = async (destFormato: "PDF" | "EXCEL") => {
    setDescargandoCons(destFormato);
    try {
      await reportesService.descargar(filtroConsumidor, destFormato, mesCons, incluirDetalle);
      flashCons("success", `Reporte de consumidores ${destFormato} descargado.`);
    } catch (err) {
      flashCons("error", await mensajeDeError(err, "Ocurrió un error al generar el reporte."));
    } finally {
      setDescargandoCons(null);
    }
  };

  const descargaSolDeshabilitada = descargandoSol !== null || rangoInvalido || !stats || sinDatos || loadStats;

  const inputCls = "px-3 py-2 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none";

  return (
    <Layout>
      <div className="space-y-5">

        {/* TÍTULO */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-navbar rounded-xl flex items-center justify-center">
            <BarChart3 className="w-5 h-5 text-navbar-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Reportes</h1>
            <p className="text-muted-foreground text-sm">Estadísticas y reportes del sistema ANH</p>
          </div>
        </div>

        {/* TABS */}
        <div className="flex gap-2 border-b border-border">
          <button
            onClick={() => setTab("solicitudes")}
            className={`px-5 py-2.5 text-sm font-medium rounded-t-xl transition-colors ${
              tab === "solicitudes"
                ? "bg-navbar text-navbar-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Solicitudes
          </button>
          <button
            onClick={() => setTab("consumidores")}
            className={`px-5 py-2.5 text-sm font-medium rounded-t-xl transition-colors ${
              tab === "consumidores"
                ? "bg-navbar text-navbar-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Consumidores
          </button>
        </div>

        {/* TAB SOLICITUDES */}
        {tab === "solicitudes" && (
          <div className="space-y-5">

            {alertaSol && <Alert type={alertaSol.type} message={alertaSol.message} />}

            {/* FILTROS (se aplican automáticamente al cambiar) */}
            <Card>
              <CardBody className="p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Filter className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium text-foreground">Filtros</span>
                  {loadStats && <Spinner size="sm" />}
                </div>
                <div className="flex flex-wrap gap-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-muted-foreground">Desde</label>
                    <input type="date" value={fechaDesde} onChange={e => setFechaDesde(e.target.value)} className={inputCls} />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-muted-foreground">Hasta</label>
                    <input type="date" value={fechaHasta} onChange={e => setFechaHasta(e.target.value)} className={inputCls} />
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-muted-foreground">Estado</label>
                    <select value={estadoFiltro} onChange={e => setEstadoFiltro(e.target.value)} className={inputCls}>
                      {ESTADOS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-muted-foreground">Combustible</label>
                    <select value={combustibleFiltro} onChange={e => setCombustibleFiltro(e.target.value)} className={inputCls}>
                      <option value="">Todos</option>
                      <option value="GASOLINA">Gasolina</option>
                      <option value="DIESEL">Diésel</option>
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-muted-foreground">Estación</label>
                    <select value={estacionFiltro} onChange={e => setEstacionFiltro(e.target.value)} className={inputCls}>
                      <option value="">Todas</option>
                      {estaciones.map(e => <option key={e.id} value={e.id}>{e.nombre}</option>)}
                    </select>
                  </div>
                </div>

                {rangoInvalido ? (
                  <Alert type="error" message="La fecha 'desde' no puede ser posterior a la fecha 'hasta'." className="mt-3" />
                ) : stats && (
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground mt-3">
                    <CalendarRange className="w-3.5 h-3.5" />
                    {stats.periodo.texto}
                  </p>
                )}
              </CardBody>
            </Card>

            {/* MÉTRICAS Y GRÁFICOS */}
            {stats && !rangoInvalido && (
              sinDatos ? (
                <Card>
                  <CardBody className="text-center py-12">
                    <p className="text-foreground font-medium mb-1">{SIN_DATOS}</p>
                    <p className="text-muted-foreground text-sm">Ajusta el rango de fechas o los filtros e inténtalo de nuevo.</p>
                  </CardBody>
                </Card>
              ) : (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <Metrica label="Total de solicitudes" value={stats.total.toLocaleString("es-BO")} />
                    <Metrica label="Litros despachados"   value={formatLitros(stats.litros_despachados)} />
                    <Metrica label="Tasa de aprobación"   value={formatTasa(stats.tasa_aprobacion)} />
                    <Metrica label="Tasa de rechazo"      value={formatTasa(stats.tasa_rechazo)} />
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    {/* Estados — dona */}
                    <Grafico titulo="Solicitudes por estado">
                      <ResponsiveContainer width="100%" height={260}>
                        <PieChart>
                          <Pie
                            data={stats.por_estado}
                            dataKey="total"
                            nameKey="estado"
                            cx="50%"
                            cy="45%"
                            innerRadius={55}
                            outerRadius={85}
                            paddingAngle={2}
                          >
                            {stats.por_estado.map(entry => (
                              <Cell key={entry.estado} fill={ESTADOS_SOLICITUD_HEX[entry.estado] ?? "#CBD5E1"} />
                            ))}
                          </Pie>
                          <Tooltip {...tooltipStyle} formatter={(v, n) => [`${v} solicitudes`, ESTADOS_SOLICITUD[String(n)]?.label ?? n]} />
                          <Legend
                            formatter={(valor: string) => {
                              const fila = stats.por_estado.find(e => e.estado === valor);
                              return `${ESTADOS_SOLICITUD[valor]?.label ?? valor} (${fila?.total ?? 0})`;
                            }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    </Grafico>

                    {/* Litros despachados por combustible */}
                    <Grafico titulo="Litros despachados por combustible">
                      <ResponsiveContainer width="100%" height={260}>
                        <BarChart data={stats.despachados_por_combustible} margin={{ top: 20, right: 20, left: 0, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="etiqueta" tick={{ fontSize: 12 }} />
                          <YAxis tick={{ fontSize: 11 }} />
                          <Tooltip {...tooltipStyle} formatter={(v) => [formatLitros(Number(v)), "Despachado"]} />
                          <Bar dataKey="litros" name="Litros despachados" fill={ESTADOS_SOLICITUD_HEX.DESPACHADA} radius={[4, 4, 0, 0]}>
                            <LabelList dataKey="litros" position="top" formatter={(v: number) => formatLitros(v)} style={{ fontSize: 11 }} />
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </Grafico>
                  </div>

                  {/* Evolución — creadas / aprobadas alguna vez / despachadas */}
                  <Grafico titulo={`Evolución ${stats.evolucion.agrupacion === "dia" ? "diaria" : "mensual"} (por fecha de creación)`}>
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart data={stats.evolucion.puntos} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="etiqueta" tick={{ fontSize: 11 }} />
                        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                        <Tooltip {...tooltipStyle} />
                        <Legend />
                        <Bar dataKey="creadas"     name="Creadas"                fill={COLOR_CREADAS} />
                        <Bar dataKey="aprobadas"   name="Aprobadas alguna vez"   fill={ESTADOS_SOLICITUD_HEX.APROBADA} />
                        <Bar dataKey="despachadas" name="Despachadas"            fill={ESTADOS_SOLICITUD_HEX.DESPACHADA} />
                      </BarChart>
                    </ResponsiveContainer>
                  </Grafico>

                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    <Grafico titulo="Top estaciones (litros despachados)">
                      {stats.por_estacion.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-10">Sin despachos en el rango.</p>
                      ) : (
                        <ResponsiveContainer width="100%" height={260}>
                          <BarChart data={stats.por_estacion} layout="vertical" margin={{ top: 0, right: 60, left: 10, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis type="number" tick={{ fontSize: 11 }} />
                            <YAxis dataKey="nombre" type="category" tick={{ fontSize: 10 }} width={120} />
                            <Tooltip {...tooltipStyle} formatter={(v) => [formatLitros(Number(v)), "Despachado"]} />
                            <Bar dataKey="litros_despachados" name="Litros despachados" fill={ESTADOS_SOLICITUD_HEX.DESPACHADA} radius={[0, 4, 4, 0]}>
                              <LabelList dataKey="litros_despachados" position="right" formatter={(v: number) => formatLitros(v)} style={{ fontSize: 11 }} />
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      )}
                    </Grafico>

                    <Grafico titulo="Top municipios (litros despachados)">
                      {stats.por_municipio.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-10">Sin despachos en el rango.</p>
                      ) : (
                        <ResponsiveContainer width="100%" height={260}>
                          <BarChart data={stats.por_municipio} layout="vertical" margin={{ top: 0, right: 60, left: 10, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis type="number" tick={{ fontSize: 11 }} />
                            <YAxis dataKey="municipio" type="category" tick={{ fontSize: 10 }} width={100} />
                            <Tooltip {...tooltipStyle} formatter={(v) => [formatLitros(Number(v)), "Despachado"]} />
                            <Bar dataKey="litros_despachados" name="Litros despachados" fill={ESTADOS_SOLICITUD_HEX.APROBADA} radius={[0, 4, 4, 0]}>
                              <LabelList dataKey="litros_despachados" position="right" formatter={(v: number) => formatLitros(v)} style={{ fontSize: 11 }} />
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      )}
                    </Grafico>
                  </div>
                </>
              )
            )}

            {loadStats && !stats && (
              <div className="flex items-center justify-center py-16">
                <Spinner size="lg" />
              </div>
            )}

            {/* DESCARGA — un clic por formato, sin paso intermedio de selección */}
            <div className="bg-navbar rounded-2xl p-6 text-navbar-foreground">
              <h3 className="font-semibold mb-1">Descargar reporte de solicitudes</h3>
              <p className="text-navbar-muted text-xs mb-4">
                {sinDatos
                  ? SIN_DATOS
                  : "Se descarga con los mismos filtros aplicados arriba."}
              </p>
              <div className="flex gap-3">
                <Button
                  variant="primary"
                  icon={<FileSpreadsheet className="w-4 h-4" />}
                  loading={descargandoSol === "EXCEL"}
                  disabled={descargaSolDeshabilitada}
                  onClick={() => descargarSolicitudes("EXCEL")}
                  className="flex-1"
                >
                  Descargar Excel
                </Button>
                <Button
                  variant="secondary"
                  icon={<FileText className="w-4 h-4" />}
                  loading={descargandoSol === "PDF"}
                  disabled={descargaSolDeshabilitada}
                  onClick={() => descargarSolicitudes("PDF")}
                  className="flex-1"
                >
                  Descargar PDF
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* TAB CONSUMIDORES */}
        {tab === "consumidores" && (
          <div className="max-w-2xl space-y-5">

            {alertaCons && <Alert type={alertaCons.type} message={alertaCons.message} />}

            <Card>
              <CardHeader><h2 className="font-semibold text-foreground">Reporte de consumidores</h2></CardHeader>
              <CardBody className="space-y-5">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-3">Tipo de reporte</label>
                  <div className="grid grid-cols-1 gap-2">
                    {FILTROS_CONSUMIDORES.map(f => (
                      <label key={f.value} className={`flex items-center gap-3 p-4 rounded-xl border cursor-pointer transition-colors ${
                        filtroConsumidor === f.value ? "border-primary bg-primary/10" : "border-border hover:bg-background"
                      }`}>
                        <input type="radio" name="filtro_cons" value={f.value} checked={filtroConsumidor === f.value}
                          onChange={() => setFiltroConsumidor(f.value)} className="text-primary accent-primary" />
                        <p className={`text-sm font-medium ${filtroConsumidor === f.value ? "text-primary" : "text-foreground"}`}>
                          {f.label}
                        </p>
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">Mes</label>
                  <input
                    type="month"
                    value={mesCons}
                    max={mesActual()}
                    onChange={e => setMesCons(e.target.value || mesActual())}
                    className={inputCls}
                  />
                </div>

                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={incluirDetalle}
                    onChange={e => setIncluirDetalle(e.target.checked)}
                    className="mt-0.5 accent-primary"
                  />
                  <span>
                    <span className="block text-sm font-medium text-foreground">Incluir detalle de solicitudes</span>
                    <span className="block text-xs text-muted-foreground">
                      Agrega las solicitudes del mes de cada consumidor (en el Excel, en una hoja "Detalle").
                    </span>
                  </span>
                </label>
              </CardBody>
            </Card>

            <div className="bg-navbar rounded-2xl p-6 text-navbar-foreground">
              <h3 className="font-semibold mb-1">Resumen</h3>
              <p className="text-navbar-muted text-sm mb-4">
                {FILTROS_CONSUMIDORES.find(f => f.value === filtroConsumidor)?.label} · {mesCons}
                {incluirDetalle && " · con detalle"}
              </p>
              <div className="flex gap-3">
                <Button
                  variant="primary"
                  icon={<FileSpreadsheet className="w-4 h-4" />}
                  loading={descargandoCons === "EXCEL"}
                  disabled={descargandoCons !== null}
                  onClick={() => descargarConsumidores("EXCEL")}
                  className="flex-1"
                >
                  Descargar Excel
                </Button>
                <Button
                  variant="secondary"
                  icon={<FileText className="w-4 h-4" />}
                  loading={descargandoCons === "PDF"}
                  disabled={descargandoCons !== null}
                  onClick={() => descargarConsumidores("PDF")}
                  className="flex-1"
                >
                  Descargar PDF
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
