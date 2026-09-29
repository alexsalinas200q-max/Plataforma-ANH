// src/pages/anh/Solicitudes.tsx

import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Layout from "../../components/Layout";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { Spinner } from "../../components/ui/Spinner";
import { EstadoSolicitudBadge } from "../../components/ui/EstadoBadge";
import { solicitudesService } from "../../services/solicitudes.service";
import { estacionesService } from "../../services/estaciones.service";
import type { Solicitud } from "../../types/solicitud.types";
import { COMBUSTIBLES } from "../../utils/constants";
import { formatFecha, formatIdPublico } from "../../utils/format";
import {
  FileText, Search, RefreshCw, ChevronLeft, ChevronRight, Building2, X,
} from "lucide-react";

// ------------------------------------------------
// CONSTANTES
// ------------------------------------------------

// Todos los estados como pestañas: la barra ya tiene scroll
// horizontal. (Antes Rechazadas/Canceladas/Expiradas iban en un menú
// "Más" que quedaba recortado por ese mismo overflow y no se veía.)
const TABS = [
  { value: "",           label: "Todas" },
  { value: "PENDIENTE",  label: "Pendientes" },
  { value: "OBSERVADA",  label: "Observadas" },
  { value: "APROBADA",   label: "Aprobadas" },
  { value: "DESPACHADA", label: "Despachadas" },
  { value: "RECHAZADA",  label: "Rechazadas" },
  { value: "CANCELADA",  label: "Canceladas" },
  { value: "EXPIRADA",   label: "Expiradas" },
];

const POR_PAGINA = 20;

// ------------------------------------------------
// COMPONENTE PRINCIPAL
// ------------------------------------------------

export default function SolicitudesANH() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [solicitudes, setSolicitudes] = useState<Solicitud[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState("");
  const [total,       setTotal]       = useState(0);

  // El estado inicial se lee de los query params del URL
  // (ej. ?estado=PENDIENTE desde un atajo del Dashboard).
  const [estado,        setEstado]        = useState(() => searchParams.get("estado") ?? "PENDIENTE");
  const [busqueda,      setBusqueda]      = useState("");
  const [busquedaInput, setBusquedaInput] = useState("");
  const [pagina,        setPagina]        = useState(1);

  // Filtro por estación (?estacion=<id>), p. ej. desde "Ver solicitudes
  // de esta estación" en el detalle de estación. Se combina con el tab
  // y la búsqueda.
  const [estacionId,     setEstacionId]     = useState(() => searchParams.get("estacion") ?? "");
  const [estacionNombre, setEstacionNombre] = useState("");

  // ------------------------------------------------
  // CARGA DE DATOS
  // La búsqueda funciona DENTRO del estado activo:
  // ambos params se envían al backend simultáneamente.
  // ------------------------------------------------

  const cargar = useCallback(async (
    paginaActual: number,
    estadoActual: string,
    busquedaActual: string,
    estacionActual: string,
  ) => {
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = {
        page: String(paginaActual),
      };
      if (estadoActual) params.estado = estadoActual;
      if (busquedaActual) params.search = busquedaActual;
      if (estacionActual) params.estacion_servicio = estacionActual;

      const res = await solicitudesService.getAll(params);
      setSolicitudes(res.results ?? []);
      setTotal(res.count ?? 0);
    } catch {
      setError("Error al cargar las solicitudes.");
      setSolicitudes([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar(pagina, estado, busqueda, estacionId);
  }, [pagina, estado, busqueda, estacionId, cargar]);

  // Nombre de la estación filtrada, para el chip
  useEffect(() => {
    if (!estacionId) return;
    estacionesService.getById(Number(estacionId))
      .then(e => setEstacionNombre(e.nombre))
      .catch(() => setEstacionNombre(`#${estacionId}`));
  }, [estacionId]);

  // Sincronizar el query param ?estado= con el tab activo
  // para que el URL refleje el estado y se pueda compartir/recargar.
  useEffect(() => {
    const params: Record<string, string> = {};
    if (estado) params.estado = estado;
    if (estacionId) params.estacion = estacionId;
    setSearchParams(params, { replace: true });
  }, [estado, estacionId, setSearchParams]);

  const onQuitarEstacion = () => {
    setEstacionId("");
    setEstacionNombre("");
    setPagina(1);
  };

  const onBuscar = (e: React.FormEvent) => {
    e.preventDefault();
    setPagina(1);
    setBusqueda(busquedaInput);
  };

  const onLimpiarBusqueda = () => {
    setBusquedaInput("");
    setBusqueda("");
    setPagina(1);
  };

  const onTabChange = (nuevoEstado: string) => {
    setEstado(nuevoEstado);
    setPagina(1);
  };

  const totalPaginas = total > 0 ? Math.ceil(total / POR_PAGINA) : 1;

  return (
    <Layout>
      <div className="space-y-5">

        {/* TÍTULO */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-navbar rounded-xl flex items-center justify-center">
              <FileText className="w-5 h-5 text-navbar-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Solicitudes</h1>
              <p className="text-muted-foreground text-sm">{total} solicitudes encontradas</p>
            </div>
          </div>
          <Button
            variant="outline"
            icon={<RefreshCw className="w-4 h-4" />}
            onClick={() => cargar(pagina, estado, busqueda, estacionId)}
          >
            Actualizar
          </Button>
        </div>

        {error && <Alert type="error" message={error} />}

        {/* TABLA CON TABS */}
        <Card>

          {/* TABS DE ESTADO */}
          <div className="flex items-center border-b border-border overflow-x-auto">
            {TABS.map(tab => (
              <button
                key={tab.value}
                onClick={() => onTabChange(tab.value)}
                className={`px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                  estado === tab.value
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* BÚSQUEDA (funciona dentro del tab activo) */}
          <div className="px-4 pt-4 pb-2">
            <form onSubmit={onBuscar} className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                  value={busquedaInput}
                  onChange={e => setBusquedaInput(e.target.value)}
                  placeholder={`Buscar${estado ? ` en ${TABS.find(e => e.value === estado)?.label?.toLowerCase() ?? estado.toLowerCase()}` : ""}...`}
                  className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none"
                />
              </div>
              <Button variant="primary" size="md" type="submit">
                Buscar
              </Button>
              {busqueda && (
                <Button variant="outline" size="md" type="button" onClick={onLimpiarBusqueda}>
                  Limpiar
                </Button>
              )}
            </form>
            {estacionId && (
              <div className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-primary/10 text-primary">
                <Building2 className="w-3.5 h-3.5" />
                Estación: {estacionNombre || `#${estacionId}`}
                <button type="button" onClick={onQuitarEstacion} className="hover:text-primary-hover" aria-label="Quitar filtro de estación">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
            {busqueda && (
              <p className="text-xs text-primary mt-2">
                Resultados para "<strong>{busqueda}</strong>"
                {estado && ` en ${TABS.find(e => e.value === estado)?.label?.toLowerCase()}`}
              </p>
            )}
          </div>

          {/* TABLA */}
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Spinner size="lg" />
            </div>
          ) : solicitudes.length === 0 ? (
            <div className="text-center py-16 px-4">
              <FileText className="w-12 h-12 text-border mx-auto mb-3" />
              <p className="text-foreground font-medium mb-1">
                {busqueda ? "Sin resultados" : "Sin solicitudes"}
              </p>
              <p className="text-muted-foreground text-sm">
                {busqueda
                  ? `No se encontraron solicitudes para "${busqueda}"${estado ? ` en ${TABS.find(e => e.value === estado)?.label?.toLowerCase()}` : ""}.`
                  : "No hay solicitudes en este estado."
                }
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      N° Solicitud
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Consumidor
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Litros
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Estado
                    </th>
                    <th className="px-4 py-3 w-8"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {solicitudes.map(s => {
                    const consumidorNombre =
                      (s.consumidor as any)?.nombre_completo ||
                      (s as any).consumidor_nombre || "—";
                    const combustible = COMBUSTIBLES[s.tipo_combustible] ?? s.tipo_combustible;
                    const fecha = formatFecha(s.fecha_creacion);

                    return (
                      <tr
                        key={s.id_publico}
                        onClick={() => navigate(`/anh/solicitudes/${s.id_publico}`)}
                        className="hover:bg-background transition-colors cursor-pointer group"
                      >
                        <td className="px-4 py-3 text-sm font-mono font-medium text-foreground">
                          #{formatIdPublico(s.id_publico)}
                        </td>
                        <td className="px-4 py-3">
                          <p className="text-sm text-foreground">{consumidorNombre}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {combustible} · {fecha}
                          </p>
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">
                          {s.litros_solicitados} L
                        </td>
                        <td className="px-4 py-3">
                          <EstadoSolicitudBadge estado={s.estado} />
                        </td>
                        <td className="px-4 py-3 text-right">
                          <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* PAGINACIÓN */}
          {totalPaginas > 1 && (
            <div className="px-4 py-3 border-t border-border flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                Página {pagina} de {totalPaginas} · {total} resultados
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  icon={<ChevronLeft className="w-3.5 h-3.5" />}
                  onClick={() => setPagina(p => Math.max(1, p - 1))}
                  disabled={pagina === 1 || loading}
                >
                  Anterior
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPagina(p => Math.min(totalPaginas, p + 1))}
                  disabled={pagina >= totalPaginas || loading}
                >
                  Siguiente
                  <ChevronRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          )}
        </Card>
      </div>
    </Layout>
  );
}