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
  descargar: async (
    filtro: string,
    formato: "PDF" | "EXCEL",
    mes: string,
    incluirDetalle: boolean,
  ): Promise<void> => {
    const res = await api.get("/api/reportes/consumidores/", {
      params:       { filtro, formato, mes, incluir_detalle: incluirDetalle ? "true" : "false" },
      responseType: "blob",
    });
    const ext = formato === "PDF" ? "pdf" : "xlsx";
    guardarBlob(res.data, nombreDeArchivo(res.headers["content-disposition"], `reporte_consumidores_${mes}.${ext}`));
  },

  getDashboard: async () => {
    const res = await api.get("/api/dashboard/");
    return res.data;
  },
};
