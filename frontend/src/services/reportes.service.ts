// src/services/reportes.service.ts

import { api } from "../context/AuthContext";

// Nombre del archivo que manda el backend (incluye el período, ej.
// reporte_solicitudes_2026-09-01_2026-09-30.pdf). El backend expone
// Content-Disposition por CORS; si no llegara, se usa el de respaldo.
function nombreDeArchivo(contentDisposition: string | undefined, respaldo: string): string {
  const match = contentDisposition?.match(/filename="?([^";]+)"?/i);
  return match?.[1] ?? respaldo;
}

function guardarBlob(data: BlobPart, nombre: string): void {
  const url = URL.createObjectURL(new Blob([data]));
  const a   = document.createElement("a");
  a.href     = url;
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(url);
}

// Con responseType "blob", el cuerpo de un 400/404 también llega como
// Blob: se lee para mostrar el mensaje del backend.
export async function mensajeDeErrorDescarga(err: unknown, porDefecto: string): Promise<string> {
  const data = (err as { response?: { data?: unknown } }).response?.data;
  try {
    if (data instanceof Blob) {
      const json = JSON.parse(await data.text());
      if (typeof json.detail === "string") return json.detail;
    }
  } catch { /* cuerpo no JSON: mensaje por defecto */ }
  return porDefecto;
}

export const reportesService = {

  // Pestaña Solicitudes: indicadores y datos de los gráficos.
  getEstadisticas: async (params: Record<string, string>) => {
    const res = await api.get("/api/estadisticas/solicitudes/", { params });
    return res.data;
  },

  // Reporte de solicitudes con los mismos filtros que la pantalla.
  descargarSolicitudes: async (
    params: Record<string, string>,
    formato: "PDF" | "EXCEL",
  ): Promise<void> => {
    const res = await api.get("/api/reportes/solicitudes/", {
      params:       { ...params, formato },
      responseType: "blob",
    });
    const ext = formato === "PDF" ? "pdf" : "xlsx";
    guardarBlob(res.data, nombreDeArchivo(res.headers["content-disposition"], `reporte_solicitudes.${ext}`));
  },

  // mes: "AAAA-MM". filtro: TODOS | CUPO_AGOTADO | BLOQUEADOS | EN_REVISION.
  // consumidorId (id de perfil): reporte de un solo consumidor; el backend
  // ignora filtro e incluir_detalle y siempre agrega el detalle.
  descargar: async (
    filtro: string,
    formato: "PDF" | "EXCEL",
    mes: string,
    incluirDetalle: boolean,
    consumidorId?: number,
  ): Promise<void> => {
    const params: Record<string, string> = {
      filtro, formato, mes, incluir_detalle: incluirDetalle ? "true" : "false",
    };
    if (consumidorId) params.consumidor_id = String(consumidorId);
    const res = await api.get("/api/reportes/consumidores/", { params, responseType: "blob" });
    const ext = formato === "PDF" ? "pdf" : "xlsx";
    guardarBlob(res.data, nombreDeArchivo(res.headers["content-disposition"], `reporte_consumidores_${mes}.${ext}`));
  },

  getDashboard: async () => {
    const res = await api.get("/api/dashboard/");
    return res.data;
  },
};
