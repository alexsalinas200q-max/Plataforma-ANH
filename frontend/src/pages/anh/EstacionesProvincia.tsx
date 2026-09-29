// src/pages/anh/EstacionesProvincia.tsx
// Nivel 3: Estaciones agrupadas por municipio dentro de una provincia

import { useState, useEffect, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Layout from "../../components/Layout";
import { estacionesService } from "../../services/estaciones.service";
import { catalogosService } from "../../services/catalogos.service";
import type { EstacionServicio, EstadoEstacion } from "../../types/estacion.types";
import { Card, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Spinner } from "../../components/ui/Spinner";
import { Alert } from "../../components/ui/Alert";
import { Modal } from "../../components/ui/Modal";
import { formatFecha } from "../../utils/format";
import {
  Building2, ChevronRight, ArrowLeft, Search, Edit2, Eye, FileText,
  User, Mail, Phone, CheckCircle, AlertTriangle,
} from "lucide-react";

interface Operador {
  id: number;
  nombre_completo: string;
  email: string;
  cargo: string;
  celular: string;
}

// GET /api/estaciones/{id}/ (EstacionServicioReadSerializer)
interface EstacionDetalle extends EstacionServicio {
  operadores?:          Operador[];
  // Solo cuenta APROBADAS y DESPACHADAS (ver get_total_solicitudes).
  total_solicitudes?:   number;
  creada_por_nombre?:   string | null;
  fecha_creacion?:      string;
  fecha_actualizacion?: string;
}

function Campo({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground mb-0.5">{label}</p>
      <p className="text-sm font-medium text-foreground">{value ?? "—"}</p>
    </div>
  );
}

interface Prov { id: number; nombre: string; }
interface Muni { id: number; nombre: string; }

const ESTADOS_FILTRO: { value: EstadoEstacion | ""; label: string }[] = [
  { value: "",           label: "Todos" },
  { value: "ACTIVA",     label: "Activa" },
  { value: "INACTIVA",   label: "Inactiva" },
  { value: "SUSPENDIDA", label: "Suspendida" },
];

const estadoColor: Record<string, string> = {
  ACTIVA:     "bg-state-success-bg text-state-success-fg",
  INACTIVA:   "bg-background text-muted-foreground",
  SUSPENDIDA: "bg-red-100 text-red-600",
};

export default function EstacionesProvincia() {
  const { deptoId, provId } = useParams<{ deptoId: string; provId: string }>();
  const navigate = useNavigate();
  const deptoIdNum = Number(deptoId);
  const provIdNum  = Number(provId);

  const [estaciones, setEstaciones] = useState<EstacionServicio[]>([]);
  const [deptoNombre, setDeptoNombre] = useState("");
  const [provNombre,  setProvNombre]  = useState("");
  const [loading,       setLoading]       = useState(true);
  const [alerta,        setAlerta]        = useState<{ type: "error" | "success"; message: string } | null>(null);
  const [busqueda,      setBusqueda]      = useState("");
  const [filtroEstado,  setFiltroEstado]  = useState<EstadoEstacion | "">("");

  // Operadores lazy — el conteo ya viene en el listado
  // (operadores_count); el detalle (nombre/email/celular) se
  // carga bajo demanda al expandir.
  const [expOperadores, setExpOperadores] = useState<Set<number>>(new Set());
  const [cargandoOperadores, setCargandoOperadores] = useState<Set<number>>(new Set());
  const [operadoresCache, setOperadoresCache] = useState<Record<number, Operador[]>>({});

  // Modal detalle (solo lectura)
  const [detalleId,       setDetalleId]       = useState<number | null>(null);
  const [detalle,         setDetalle]         = useState<EstacionDetalle | null>(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  const [errorDetalle,    setErrorDetalle]    = useState("");

  // Modal editar
  const [modal,     setModal]     = useState(false);
  const [editando,  setEditando]  = useState<EstacionServicio | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [errorForm, setErrorForm] = useState("");
  const [formEdit, setFormEdit] = useState({
    nombre: "", codigo: "", direccion: "", estado: "ACTIVA" as EstadoEstacion,
  });

  // Catálogos para el modal de editar (municipio)
  const [munis,  setMunis]  = useState<Muni[]>([]);
  const [formMuniId, setFormMuniId] = useState(0);
  const [loadingCatalogo, setLoadingCatalogo] = useState(false);

  const cargar = async () => {
    setLoading(true);
    try {
      // Estaciones de este departamento (filtro backend)
      const data = await estacionesService.getTodas({
        municipio__provincia__departamento: String(deptoIdNum),
      });
      setEstaciones(data);

      // Nombres para breadcrumb
      if (data.length > 0) {
        setDeptoNombre(data[0].departamento_nombre);
      } else {
        const deptos = await catalogosService.getDepartamentos();
        const d = deptos.find((x: Prov) => x.id === deptoIdNum);
        setDeptoNombre(d?.nombre ?? `Departamento ${deptoId}`);
      }

      const provs = await catalogosService.getProvincias(deptoIdNum);
      const p = provs.find((x: Prov) => x.id === provIdNum);
      setProvNombre(p?.nombre ?? `Provincia ${provId}`);
    } catch {
      setAlerta({ type: "error", message: "Error al cargar las estaciones." });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { cargar(); }, [deptoIdNum, provIdNum]);

  // Filtrar: solo estaciones de esta provincia + búsqueda + estado
  const estacionesFiltradas = useMemo(() => {
    return estaciones
      .filter(e => e.provincia_id === provIdNum)
      .filter(e => !filtroEstado || e.estado === filtroEstado)
      .filter(e => {
        if (!busqueda) return true;
        const q = busqueda.toLowerCase();
        return (
          e.nombre.toLowerCase().includes(q) ||
          e.codigo.toLowerCase().includes(q) ||
          e.direccion.toLowerCase().includes(q) ||
          e.municipio_nombre.toLowerCase().includes(q)
        );
      });
  }, [estaciones, provIdNum, busqueda, filtroEstado]);

  // Agrupar por municipio
  const porMunicipio = useMemo(() => {
    const mapa = new Map<number, { nombre: string; estaciones: EstacionServicio[] }>();
    estacionesFiltradas.forEach(e => {
      if (!mapa.has(e.municipio)) {
        mapa.set(e.municipio, { nombre: e.municipio_nombre, estaciones: [] });
      }
      mapa.get(e.municipio)!.estaciones.push(e);
    });
    return [...mapa.entries()]
      .map(([id, data]) => ({ id, ...data }))
      .sort((a, b) => a.nombre.localeCompare(b.nombre));
  }, [estacionesFiltradas]);

  // Operadores lazy
  const toggleOperadores = async (estacionId: number) => {
    if (expOperadores.has(estacionId)) {
      const s = new Set(expOperadores); s.delete(estacionId); setExpOperadores(s);
      return;
    }
    setExpOperadores(prev => new Set(prev).add(estacionId));
    if (operadoresCache[estacionId]) return;

    setCargandoOperadores(prev => new Set(prev).add(estacionId));
    try {
      const detalle = await estacionesService.getById(estacionId) as EstacionDetalle;
      setOperadoresCache(prev => ({ ...prev, [estacionId]: detalle.operadores ?? [] }));
    } catch {
      setOperadoresCache(prev => ({ ...prev, [estacionId]: [] }));
    } finally {
      setCargandoOperadores(prev => { const s = new Set(prev); s.delete(estacionId); return s; });
    }
  };

  // Detalle
  const verDetalle = async (estacionId: number) => {
    setDetalleId(estacionId);
    setDetalle(null);
    setErrorDetalle("");
    setCargandoDetalle(true);
    try {
      const d = await estacionesService.getById(estacionId) as EstacionDetalle;
      setDetalle(d);
      // Aprovecha para llenar la caché de operadores de la tarjeta
      setOperadoresCache(prev => ({ ...prev, [estacionId]: d.operadores ?? [] }));
    } catch {
      setErrorDetalle("No se pudo cargar el detalle de la estación.");
    } finally {
      setCargandoDetalle(false);
    }
  };

  // Editar
  const abrirEditar = async (e: EstacionServicio) => {
    setEditando(e);
    setErrorForm("");
    setFormEdit({ nombre: e.nombre, codigo: e.codigo, direccion: e.direccion, estado: e.estado });
    setFormMuniId(e.municipio);

    // Cargar municipios de la provincia actual para el select
    setLoadingCatalogo(true);
    try { setMunis(await catalogosService.getMunicipios(provIdNum)); }
    finally { setLoadingCatalogo(false); }
    setModal(true);
  };

  const guardarEdicion = async () => {
    if (!formEdit.nombre || !formEdit.codigo || !formEdit.direccion || !formMuniId) {
      setErrorForm("Completa todos los campos obligatorios.");
      return;
    }
    setGuardando(true); setErrorForm("");
    try {
      await estacionesService.actualizar(editando!.id, {
        nombre: formEdit.nombre, codigo: formEdit.codigo, direccion: formEdit.direccion,
        municipio: formMuniId, estado: formEdit.estado,
      });
      setAlerta({ type: "success", message: "Estación actualizada correctamente." });
      setModal(false);
      await cargar();
    } catch (err: unknown) {
      const e = err as { response?: { data?: Record<string, string[]> } };
      const data = e.response?.data;
      if (data) {
        setErrorForm(Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v[0] : v}`).join(" | "));
      } else {
        setErrorForm("Error al guardar la estación.");
      }
    } finally { setGuardando(false); }
  };

  const cambiarEstado = async (id: number, estado: EstadoEstacion) => {
    try {
      await estacionesService.cambiarEstado(id, estado);
      setAlerta({ type: "success", message: `Estado cambiado a ${estado}.` });
      await cargar();
    } catch {
      setAlerta({ type: "error", message: "Error al cambiar el estado." });
    }
  };

  const inputCls = "w-full px-4 py-2.5 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none";

  return (
    <Layout>
      <div className="space-y-5">

        {/* BREADCRUMB + TÍTULO */}
        <div>
          <button
            onClick={() => navigate(`/anh/estaciones/departamento/${deptoId}`)}
            className="flex items-center gap-1.5 text-sm text-primary hover:text-primary-hover transition-colors mb-3"
          >
            <ArrowLeft className="w-4 h-4" /> {deptoNombre}
          </button>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-navbar rounded-xl flex items-center justify-center">
              <Building2 className="w-5 h-5 text-navbar-foreground" />
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-0.5">
                <span>Estaciones</span>
                <ChevronRight className="w-3 h-3" />
                <span>{deptoNombre}</span>
                <ChevronRight className="w-3 h-3" />
                <span className="text-foreground font-medium">{provNombre}</span>
              </div>
              <h1 className="text-2xl font-bold text-foreground">{provNombre}</h1>
              <p className="text-muted-foreground text-sm">
                {estacionesFiltradas.length} estaciones en {porMunicipio.length} {porMunicipio.length === 1 ? "municipio" : "municipios"}
              </p>
            </div>
          </div>
        </div>

        {alerta && <Alert type={alerta.type} message={alerta.message} />}

        {/* FILTROS */}
        <Card>
          <CardBody className="p-4 flex gap-3 flex-wrap">
            <div className="relative flex-1 min-w-48">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                value={busqueda}
                onChange={e => setBusqueda(e.target.value)}
                placeholder="Buscar estación..."
                className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none"
              />
            </div>
            <select value={filtroEstado} onChange={e => setFiltroEstado(e.target.value as EstadoEstacion | "")}
              className="px-3 py-2.5 rounded-xl border border-border text-sm bg-input outline-none focus:border-primary focus:ring-2 focus:ring-primary/20">
              {ESTADOS_FILTRO.map(e => <option key={e.value} value={e.value}>{e.label}</option>)}
            </select>
          </CardBody>
        </Card>

        {/* ESTACIONES AGRUPADAS POR MUNICIPIO */}
        {loading ? (
          <div className="flex items-center justify-center py-16"><Spinner size="lg" /></div>
        ) : porMunicipio.length === 0 ? (
          <Card>
            <CardBody className="text-center py-16">
              <Building2 className="w-12 h-12 text-border mx-auto mb-3" />
              <p className="text-foreground font-medium mb-1">Sin estaciones</p>
              <p className="text-muted-foreground text-sm">No hay estaciones registradas en esta provincia.</p>
            </CardBody>
          </Card>
        ) : (
          <div className="space-y-6">
            {porMunicipio.map(muni => (
              <div key={muni.id}>
                <div className="flex items-center gap-2 mb-3">
                  <h2 className="text-sm font-semibold text-foreground">{muni.nombre}</h2>
                  <span className="text-xs text-muted-foreground bg-background px-2 py-0.5 rounded-full">
                    {muni.estaciones.length}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {muni.estaciones.map(e => (
                    <div key={e.id} className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
                      {/* Cabecera */}
                      <div className="px-5 py-4 border-b border-border flex items-start justify-between">
                        <div>
                          <p className="font-semibold text-foreground text-sm">{e.nombre}</p>
                          <p className="text-xs text-muted-foreground font-mono">{e.codigo}</p>
                        </div>
                        <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${estadoColor[e.estado] ?? "bg-background text-muted-foreground"}`}>
                          {e.estado}
                        </span>
                      </div>

                      {/* Dirección */}
                      <div className="px-5 py-3">
                        <p className="text-xs text-muted-foreground truncate">{e.direccion}</p>
                      </div>

                      {/* Acciones */}
                      <div className="px-5 py-3 border-t border-border flex gap-2 flex-wrap">
                        <button onClick={() => verDetalle(e.id)} className="flex items-center gap-1.5 px-3 py-1.5 bg-background text-muted-foreground rounded-lg text-xs font-medium hover:bg-border transition-colors">
                          <Eye className="w-3.5 h-3.5" /> Ver detalle
                        </button>
                        <button onClick={() => abrirEditar(e)} className="flex items-center gap-1.5 px-3 py-1.5 bg-background text-muted-foreground rounded-lg text-xs font-medium hover:bg-border transition-colors">
                          <Edit2 className="w-3.5 h-3.5" /> Editar
                        </button>
                        {e.estado !== "ACTIVA" && (
                          <button onClick={() => cambiarEstado(e.id, "ACTIVA")} className="px-3 py-1.5 bg-state-success-bg text-state-success-fg rounded-lg text-xs font-medium hover:opacity-90 transition-opacity">Activar</button>
                        )}
                        {e.estado !== "INACTIVA" && (
                          <button onClick={() => cambiarEstado(e.id, "INACTIVA")} className="px-3 py-1.5 bg-background text-muted-foreground rounded-lg text-xs font-medium hover:bg-border transition-colors">Desactivar</button>
                        )}
                        {e.estado !== "SUSPENDIDA" && (
                          <button onClick={() => cambiarEstado(e.id, "SUSPENDIDA")} className="px-3 py-1.5 bg-red-50 text-red-600 rounded-lg text-xs font-medium hover:bg-red-100 transition-colors">Suspender</button>
                        )}
                      </div>

                      {/* Operadores ESS — el conteo ya viene en el
                          listado, no hace falta expandir para verlo */}
                      <div className="px-5 py-3 border-t border-border">
                        {(e.operadores_count ?? 0) > 0 ? (
                          <>
                            <button
                              onClick={() => toggleOperadores(e.id)}
                              className="flex items-center justify-between w-full text-xs font-medium text-primary hover:text-primary-hover transition-colors"
                            >
                              <span className="flex items-center gap-1.5">
                                <User className="w-3.5 h-3.5" />
                                {e.operadores_count} {e.operadores_count === 1 ? "operador" : "operadores"}
                              </span>
                              <ChevronRight className={`w-3.5 h-3.5 transition-transform ${expOperadores.has(e.id) ? "rotate-90" : ""}`} />
                            </button>

                            {expOperadores.has(e.id) && (
                              <div className="mt-2 pt-2 border-t border-border">
                                {cargandoOperadores.has(e.id) ? (
                                  <div className="flex items-center gap-2 py-1">
                                    <Spinner size="sm" /> <span className="text-xs text-muted-foreground">Cargando...</span>
                                  </div>
                                ) : (
                                  (operadoresCache[e.id] ?? []).map(op => (
                                    <div key={op.id} className="space-y-1 py-2 border-b border-border last:border-0">
                                      <p className="text-xs font-semibold text-foreground">{op.nombre_completo}</p>
                                      <p className="text-xs text-muted-foreground">{op.cargo}</p>
                                      <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                                        <Mail className="w-3 h-3" /> {op.email}
                                      </p>
                                      {op.celular && (
                                        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                                          <Phone className="w-3 h-3" /> {op.celular}
                                        </p>
                                      )}
                                    </div>
                                  ))
                                )}
                              </div>
                            )}
                          </>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-state-warning-bg text-state-warning-fg">
                            <AlertTriangle className="w-3 h-3" />
                            Sin operadores asignados
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* MODAL DETALLE (solo lectura) */}
      <Modal open={detalleId !== null} onClose={() => setDetalleId(null)} title="Detalle de estación" size="lg">
        {cargandoDetalle ? (
          <div className="flex items-center justify-center py-10"><Spinner size="lg" /></div>
        ) : errorDetalle ? (
          <Alert type="error" message={errorDetalle} />
        ) : detalle && (
          <div className="space-y-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-foreground">{detalle.nombre}</p>
                <p className="text-xs text-muted-foreground font-mono">{detalle.codigo}</p>
              </div>
              <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${estadoColor[detalle.estado] ?? "bg-background text-muted-foreground"}`}>
                {detalle.estado}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <Campo label="Departamento" value={detalle.departamento_nombre} />
              <Campo label="Provincia"    value={provNombre || null} />
              <Campo label="Municipio"    value={detalle.municipio_nombre} />
              <Campo label="Dirección"    value={detalle.direccion} />
              <Campo label="Solicitudes aprobadas o despachadas" value={detalle.total_solicitudes} />
              <Campo label="Creada por"   value={detalle.creada_por_nombre} />
              <Campo label="Fecha de creación"     value={detalle.fecha_creacion ? formatFecha(detalle.fecha_creacion, true) : null} />
              <Campo label="Última actualización"  value={detalle.fecha_actualizacion ? formatFecha(detalle.fecha_actualizacion, true) : null} />
            </div>

            <div>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                Operadores ESS ({detalle.operadores?.length ?? 0})
              </p>
              {(detalle.operadores ?? []).length === 0 ? (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-state-warning-bg text-state-warning-fg">
                  <AlertTriangle className="w-3 h-3" />
                  Sin operadores asignados
                </span>
              ) : (
                <div className="border border-border rounded-xl divide-y divide-border">
                  {(detalle.operadores ?? []).map(op => (
                    <div key={op.id} className="px-4 py-2.5 space-y-0.5">
                      <p className="text-sm font-medium text-foreground">{op.nombre_completo}</p>
                      <p className="text-xs text-muted-foreground">{op.cargo}</p>
                      <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                        <Mail className="w-3 h-3" /> {op.email}
                      </p>
                      {op.celular && (
                        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                          <Phone className="w-3 h-3" /> {op.celular}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <Button variant="outline" onClick={() => setDetalleId(null)}>Cerrar</Button>
              <Button
                variant="primary"
                icon={<FileText className="w-4 h-4" />}
                onClick={() => navigate(`/anh/solicitudes?estado=&estacion=${detalle.id}`)}
              >
                Ver solicitudes de esta estación
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* MODAL EDITAR */}
      <Modal open={modal} onClose={() => setModal(false)} title="Editar estación" size="lg">
        <div className="space-y-4">
          {errorForm && <Alert type="error" message={errorForm} />}
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Nombre *</label>
            <input value={formEdit.nombre} onChange={e => setFormEdit(f => ({ ...f, nombre: e.target.value }))} className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Código *</label>
            <input value={formEdit.codigo} onChange={e => setFormEdit(f => ({ ...f, codigo: e.target.value }))} className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Municipio *</label>
            <select value={formMuniId} onChange={e => setFormMuniId(Number(e.target.value))} disabled={loadingCatalogo} className={inputCls + " disabled:opacity-50"}>
              <option value={0}>{loadingCatalogo ? "Cargando..." : "Seleccionar municipio..."}</option>
              {munis.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Dirección *</label>
            <input value={formEdit.direccion} onChange={e => setFormEdit(f => ({ ...f, direccion: e.target.value }))} className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Estado</label>
            <select value={formEdit.estado} onChange={e => setFormEdit(f => ({ ...f, estado: e.target.value as EstadoEstacion }))} className={inputCls}>
              <option value="ACTIVA">Activa</option>
              <option value="INACTIVA">Inactiva</option>
              <option value="SUSPENDIDA">Suspendida</option>
            </select>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="outline" onClick={() => setModal(false)}>Cancelar</Button>
            <Button variant="primary" icon={<CheckCircle className="w-4 h-4" />} loading={guardando} onClick={guardarEdicion}>Actualizar</Button>
          </div>
        </div>
      </Modal>
    </Layout>
  );
}