// src/services/solicitudes.service.ts

import { api } from "../context/AuthContext";
import type { Solicitud, SolicitudCreate, CupoMensual, CupoConsumidor } from "../types/solicitud.types";

interface PaginatedResponse {
  results: Solicitud[];
  next:    string | null;
}

async function fetchPage(
  url: string,
  params?: Record<string, string>
): Promise<PaginatedResponse> {
  const res = await api.get(url, params ? { params } : undefined);
  return res.data;
}

export const solicitudesService = {

  // ---- CONSUMIDOR ----

  getMiSolicitudActiva: async (): Promise<Solicitud | null> => {
    const res = await api.get("/api/solicitudes/");
    const activas = res.data.results ?? res.data;
    return activas.find((s: Solicitud) =>
      ["PENDIENTE", "OBSERVADA", "APROBADA"].includes(s.estado)
    ) ?? null;
  },

  getMisSolicitudes: async (): Promise<Solicitud[]> => {
    const res = await api.get("/api/solicitudes/");
    return res.data.results ?? res.data;
  },

  crear: async (data: SolicitudCreate): Promise<Solicitud> => {
    const formData = new FormData();
    formData.append("tipo_combustible", data.tipo_combustible);
    formData.append("litros_solicitados", String(data.litros_solicitados));
    formData.append("uso_combustible", data.uso_combustible);
    formData.append(
      "declaracion_jurada_confirmada",
      String(data.declaracion_jurada_confirmada)
    );
    formData.append("departamento", String(data.departamento));
    formData.append("provincia", String(data.provincia));
    formData.append("municipio", String(data.municipio));
    formData.append("estacion_servicio", String(data.estacion_servicio));
    if (data.documento_justificativo) {
      formData.append("documento_justificativo", data.documento_justificativo);
    }
    const res = await api.post("/api/solicitudes/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  responderObservacion: async (
    idPublico: string,
    respuesta: string,
    documento?: File | null,
  ): Promise<Solicitud> => {
    if (documento) {
      const formData = new FormData();
      formData.append("respuesta", respuesta);
      formData.append("documento_respuesta", documento);
      const res = await api.post(
        `/api/solicitudes/${idPublico}/responder-observacion/`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      return res.data;
    }
    const res = await api.post(
      `/api/solicitudes/${idPublico}/responder-observacion/`,
      { respuesta }
    );
    return res.data;
  },

  cancelar: async (idPublico: string): Promise<Solicitud> => {
    const res = await api.post(`/api/solicitudes/${idPublico}/cancelar/`);
    return res.data;
  },

  obtenerMiDisponible: async (): Promise<CupoMensual> => {
    const res = await api.get("/api/solicitudes/mi-disponible/");
    return res.data;
  },

  // Retorna Blob para visualización inline
  getComprobanteBlob: async (idPublico: string): Promise<Blob> => {
    const res = await api.get(`/api/solicitudes/${idPublico}/comprobante/`, {
      responseType: "blob",
    });
    return new Blob([res.data], { type: "application/pdf" });
  },

  getDeclaracionJuradaBlob: async (idPublico: string): Promise<Blob> => {
    const res = await api.get(
      `/api/solicitudes/${idPublico}/declaracion-jurada/`,
      { responseType: "blob" }
    );
    return new Blob([res.data], { type: "application/pdf" });
  },

  descargarComprobante: async (idPublico: string): Promise<void> => {
    const res = await api.get(`/api/solicitudes/${idPublico}/comprobante/`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(new Blob([res.data]));
    const a   = document.createElement("a");
    a.href    = url;
    a.download = `comprobante_${idPublico.slice(0, 8).toUpperCase()}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  },

  descargarDeclaracionJurada: async (idPublico: string): Promise<void> => {
    const res = await api.get(
      `/api/solicitudes/${idPublico}/declaracion-jurada/`,
      { responseType: "blob" }
    );
    const url = URL.createObjectURL(new Blob([res.data]));
    const a   = document.createElement("a");
    a.href    = url;
    a.download = `declaracion_jurada_${idPublico.slice(0, 8).toUpperCase()}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  },

  // ---- ANH ----

  getAll: async (params?: Record<string, string>): Promise<{
    results: Solicitud[];
    count: number;
  }> => {
    const res = await api.get("/api/solicitudes/", { params });
    return res.data;
  },

  getById: async (idPublico: string): Promise<Solicitud> => {
    const res = await api.get(`/api/solicitudes/${idPublico}/`);
    return res.data;
  },

  obtenerCupoConsumidor: async (consumidorId: number): Promise<CupoConsumidor> => {
    const res = await api.get(`/api/solicitudes/cupo-consumidor/${consumidorId}/`);
    return res.data;
  },

  aprobar: async (
    idPublico: string,
    data: {
      tipo_combustible_aprobado: string;
      litros_aprobados: number;
      estacion_servicio: number;
      observacion_anh?: string;
    }
  ): Promise<Solicitud> => {
    const res = await api.post(`/api/solicitudes/${idPublico}/aprobar/`, data);
    return res.data;
  },

  observar: async (
    idPublico: string,
    observacion_anh: string
  ): Promise<Solicitud> => {
    const res = await api.post(`/api/solicitudes/${idPublico}/observar/`, {
      observacion_anh,
    });
    return res.data;
  },

  rechazar: async (
    idPublico: string,
    observacion_anh: string
  ): Promise<Solicitud> => {
    const res = await api.post(`/api/solicitudes/${idPublico}/rechazar/`, {
      observacion_anh,
    });
    return res.data;
  },

  // ---- ESS ----

  despachar: async (
    idPublico: string,
    data: { litros_despachados: number; observacion?: string }
  ): Promise<Solicitud> => {
    const res = await api.post(`/api/solicitudes/${idPublico}/despachar/`, {
      confirmar:         true,
      litros_despachados: data.litros_despachados,
      observacion:       data.observacion ?? "",
    });
    return res.data;
  },

  // Recorre todas las páginas de DRF y acumula el historial completo
  // de despachos (estado=DESPACHADA) para el período pedido. La pantalla
  // de Historial necesita ver todos los registros del período —tanto
  // para las métricas de resumen como para la búsqueda local—, no solo
  // la primera página.
  getTodasDespachadas: async (params?: Record<string, string>): Promise<Solicitud[]> => {
    let url: string | null = "/api/solicitudes/";
    let currentParams: Record<string, string> | undefined = {
      estado: "DESPACHADA",
      ...params,
    };
    const acumulado: Solicitud[] = [];

    while (url) {
      const page = await fetchPage(url, currentParams);
      acumulado.push(...page.results);
      url = page.next;
      currentParams = undefined;
    }

    return acumulado;
  },
};