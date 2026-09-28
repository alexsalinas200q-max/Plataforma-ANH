// src/pages/estacion/Historial.tsx

import { useState, useEffect, useMemo, useCallback } from "react";
import Layout from "../../components/Layout";
import { Card } from "../../components/ui/Card";
import { Alert } from "../../components/ui/Alert";
import { Spinner } from "../../components/ui/Spinner";
import { solicitudesService } from "../../services/solicitudes.service";
import type { Solicitud } from "../../types/solicitud.types";
import { COMBUSTIBLES } from "../../utils/constants";
import { formatFecha, formatLitros, formatIdPublico, fechaLocalISO } from "../../utils/format";
import { useAuth } from "../../context/AuthContext";
import type { LucideIcon } from "lucide-react";
import {
  History, Search, Package, Droplets, TrendingUp, IdCard, Building2,
} from "lucide-react";

// ------------------------------------------------
// PERÍODOS — cada tab se traduce a un despacho_desde
// ------------------------------------------------

type Periodo = "hoy" | "7dias" | "mes" | "todo";

const PERIODOS: { value: Periodo; label: string }[] = [
  { value: "hoy",   label: "Hoy" },
  { value: "7dias", label: "Últimos 7 días" },
  { value: "mes",   label: "Este mes" },
  { value: "todo",  label: "Todo" },
];

const despachoDesde = (periodo: Periodo): string | null => {
  const hoy = new Date();

  switch (periodo) {
    case "hoy":
      return fechaLocalISO(hoy);
    case "7dias": {
      const d = new Date(hoy);
      d.setDate(d.getDate() - 6);
      return fechaLocalISO(d);
    }
    case "mes":
      return fechaLocalISO(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
    case "todo":
      return null;
  }
};

// ------------------------------------------------
// COMPONENTE PRINCIPAL
// ------------------------------------------------

export default function HistorialESS() {
  const { user } = useAuth();

  const [periodo,    setPeriodo]    = useState<Periodo>("hoy");
  const [despachos,  setDespachos]  = useState<Solicitud[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState("");
  const [busqueda,   setBusqueda]   = useState("");

  // ------------------------------------------------
  // CARGA DE DATOS — trae el período completo (todas las
  // páginas), porque el resumen y la búsqueda local necesitan
  // ver todos los despachos, no solo la primera página.
  // ------------------------------------------------

  const cargar = useCallback(async () => {
    // Sin estación asignada, el backend siempre devuelve vacío
    // (get_queryset() aísla al operador) — no vale la pena pedirlo.
    if (!user?.perfil_funcionario?.estacion_servicio) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const desde  = despachoDesde(periodo);
      const params: Record<string, string> = { ordering: "-fecha_despacho" };
      if (desde) params.despacho_desde = desde;

      const data = await solicitudesService.getTodasDespachadas(params);
      setDespachos(data);
    } catch {
      setError("Error al cargar el historial de despachos.");
    } finally {
      setLoading(false);
    }
  }, [periodo, user?.perfil_funcionario?.estacion_servicio]);

  useEffect(() => { cargar(); }, [cargar]);

  // ------------------------------------------------
  // MÉTRICAS — reflejan el período completo (no la búsqueda):
  // responden "cuánto despachó la estación", no "qué encontré".
  // ------------------------------------------------

  const cantidad   = despachos.length;
  const totalLitros = despachos.reduce((acc, s) => acc + (s.litros_despachados ?? 0), 0);
  const promedio    = cantidad > 0 ? totalLitros / cantidad : 0;

  // ------------------------------------------------
  // BÚSQUEDA LOCAL — instantánea, sin botón, sobre nombre,
  // CI y N° de solicitud. No afecta las métricas de arriba.
  // ------------------------------------------------

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return despachos;
    return despachos.filter(s =>
      s.id_publico.toLowerCase().includes(q) ||
      (s.consumidor_nombre ?? "").toLowerCase().includes(q) ||
      (s.consumidor_documento ?? "").toLowerCase().includes(q)
    );
  }, [despachos, busqueda]);

  // ------------------------------------------------
  // STAT CARD
  // ------------------------------------------------

  const Stat = ({ icon: Icon, valor, label }: {
    icon: LucideIcon; valor: string | number; label: string;
  }) => (
    <div className="rounded-xl border border-border bg-card shadow-sm p-4">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 bg-primary/10">
          <Icon className="w-4 h-4 text-primary" />
        </div>
        <div className="min-w-0">
          <p className="text-xl font-bold leading-none text-foreground">{valor}</p>
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
            Tu cuenta no tiene una estación de servicio asignada, así que no hay
            historial de despachos para mostrar. Contacta al administrador para
            que te asigne una.
          </p>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-5">

        {/* TÍTULO */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-navbar rounded-xl flex items-center justify-center">
            <History className="w-5 h-5 text-navbar-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Historial de despachos</h1>
            <p className="text-muted-foreground text-sm">
              {user?.estacion_nombre ?? "Estación"}
            </p>
          </div>
        </div>

        {/* TABS DE PERÍODO */}
        <div className="inline-flex items-center gap-1 bg-card border border-border rounded-xl p-1">
          {PERIODOS.map(p => (
            <button
              key={p.value}
              onClick={() => setPeriodo(p.value)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                periodo === p.value
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-background"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        {error && <Alert type="error" message={error} />}

        {/* STATS */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Stat icon={Package}    valor={cantidad}                        label="Despachos" />
          <Stat icon={Droplets}   valor={`${totalLitros} L`}              label="Litros entregados" />
          <Stat icon={TrendingUp} valor={`${promedio.toFixed(1)} L`}      label="Promedio por despacho" />
        </div>

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

        {busqueda && !loading && (
          <p className="text-xs text-muted-foreground -mt-2">
            {filtrados.length} de {despachos.length} resultados
          </p>
        )}

        {/* TABLA */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Spinner size="lg" />
          </div>
        ) : filtrados.length === 0 ? (
          <Card>
            <div className="text-center py-16 px-4">
              <IdCard className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
              <p className="text-foreground font-semibold">
                {busqueda ? "Sin resultados" : "Sin despachos en este período"}
              </p>
              <p className="text-muted-foreground text-sm mt-1">
                {busqueda
                  ? `Ningún despacho coincide con "${busqueda}".`
                  : "Todavía no se registraron despachos en el período seleccionado."}
              </p>
            </div>
          </Card>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-background/50 text-left text-xs text-muted-foreground uppercase tracking-wide">
                  <th className="px-4 py-3 font-medium">Consumidor</th>
                  <th className="px-4 py-3 font-medium text-right">Litros aprobados</th>
                  <th className="px-4 py-3 font-medium text-right">Litros despachados</th>
                  <th className="px-4 py-3 font-medium">Fecha</th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map(s => {
                  const parcial = (s.litros_despachados ?? 0) < (s.litros_aprobados ?? 0);
                  return (
                    <tr key={s.id_publico} className="border-b border-border last:border-0 hover:bg-background/50">
                      <td className="px-4 py-3">
                        <p className="font-medium text-foreground">{s.consumidor_nombre ?? "—"}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {s.consumidor_documento ?? "—"} · #{formatIdPublico(s.id_publico)} · {COMBUSTIBLES[s.tipo_combustible_aprobado ?? ""] ?? "—"}
                        </p>
                        {s.observacion_despacho && (
                          <p className="text-xs text-muted-foreground italic mt-0.5">
                            "{s.observacion_despacho}"
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right text-foreground">
                        {formatLitros(s.litros_aprobados)}
                      </td>
                      <td className={`px-4 py-3 text-right font-semibold ${parcial ? "text-state-warning-fg" : "text-foreground"}`}>
                        {formatLitros(s.litros_despachados)}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatFecha(s.fecha_despacho, true)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Layout>
  );
}
