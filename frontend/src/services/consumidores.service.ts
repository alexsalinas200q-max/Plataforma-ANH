// src/services/consumidores.service.ts

import { api } from "../context/AuthContext";
import type { ConsumidorPerfil } from "../types/consumidor.types";
import { fechaLocalISO } from "../utils/format";

export const consumidoresService = {

  getMiPerfil: async (): Promise<ConsumidorPerfil> => {
    const res = await api.get("/api/consumidores/me/");
    return res.data;
  },

  actualizarMiPerfil: async (data: Partial<ConsumidorPerfil>): Promise<ConsumidorPerfil> => {
    const res = await api.patch("/api/consumidores/me/", data);
    return res.data;
  },

  getAll: async (params?: Record<string, string>): Promise<{
    results: ConsumidorPerfil[];
    count: number;
  }> => {
    const res = await api.get("/api/consumidores/", { params });
    return res.data;
  },

  getById: async (id: number): Promise<ConsumidorPerfil> => {
    const res = await api.get(`/api/consumidores/${id}/`);
    return res.data;
  },

  verificarIdentidad: async (
    id: number,
    data: { estado_identidad: string; observacion?: string }
  ): Promise<ConsumidorPerfil> => {
    const res = await api.post(`/api/consumidores/${id}/verificar/`, data);
    return res.data;
  },

  cambiarAlerta: async (
    id: number,
    data: { alerta_repetitividad: string; motivo?: string }
  ): Promise<ConsumidorPerfil> => {
    const res = await api.post(`/api/consumidores/${id}/alerta/`, data);
    return res.data;
  },

  // {id} acá es el pk de ConsumidorPerfil (mismo que el resto de
  // este servicio), no el id de User — ver comentario en
  // consumidores/views.py:resetear_password.
  resetearPassword: async (id: number): Promise<{
    detail: string;
    email: string;
    email_enviado: boolean;
  }> => {
    const res = await api.post(`/api/consumidores/${id}/resetear-password/`);
    return res.data;
  },
};


// ------------------------------------------------
// src/services/estaciones.service.ts
// ------------------------------------------------

import type { EstacionServicio } from "../types/estacion.types";

export const estacionesService = {

  getAll: async (params?: Record<string, string>): Promise<EstacionServicio[]> => {
    const res = await api.get("/api/estaciones/", { params });
    return res.data.results ?? res.data;
  },

  getById: async (id: number): Promise<EstacionServicio> => {
    const res = await api.get(`/api/estaciones/${id}/`);
    return res.data;
  },

  crear: async (data: Partial<EstacionServicio>): Promise<EstacionServicio> => {
    const res = await api.post("/api/estaciones/", data);
    return res.data;
  },

  actualizar: async (
    id: number,
    data: Partial<EstacionServicio>
  ): Promise<EstacionServicio> => {
    const res = await api.put(`/api/estaciones/${id}/`, data);
    return res.data;
  },

  cambiarEstado: async (
    id: number,
    estado: string
  ): Promise<EstacionServicio> => {
    const res = await api.post(`/api/estaciones/${id}/cambiar-estado/`, { estado });
    return res.data;
  },
};


// ------------------------------------------------
// src/services/auth.service.ts
// ------------------------------------------------

export const authService = {

  registro: async (formData: FormData): Promise<void> => {
    await api.post("/api/users/registro/consumidor/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  verificarEmail: async (email: string, pin: string): Promise<void> => {
    await api.post("/api/users/auth/verificar-email/", { email, pin });
  },

  recuperarPassword: async (email: string): Promise<void> => {
    await api.post("/api/users/auth/recuperar-password/", { email });
  },

  confirmarRecuperacion: async (
    token: string,
    password: string,
    password2: string
  ): Promise<void> => {
    await api.post("/api/users/auth/recuperar-password/confirmar/", {
      token,
      password,
      password2,
    });
  },

  cambiarPassword: async (
    password_actual: string,
    password_nuevo: string,
    password_nuevo2: string
  ): Promise<void> => {
    await api.post("/api/users/auth/cambiar-password/", {
      password_actual,
      password_nuevo,
      password_nuevo2,
    });
  },
};


// ------------------------------------------------
// src/services/reportes.service.ts
// ------------------------------------------------

export const reportesService = {

  descargar: async (
    filtro: string,
    formato: "PDF" | "EXCEL",
    dias: number = 30
  ): Promise<void> => {
    const res = await api.get("/api/reportes/consumidores/", {
      params:       { filtro, formato, dias },
      responseType: "blob",
    });

    const extension = formato === "PDF" ? "pdf" : "xlsx";
    const url       = URL.createObjectURL(new Blob([res.data]));
    const a         = document.createElement("a");
    a.href          = url;
    a.download      = `reporte_ANH_${filtro}_${fechaLocalISO()}.${extension}`;
    a.click();
    URL.revokeObjectURL(url);
  },

  getDashboard: async () => {
    const res = await api.get("/api/dashboard/");
    return res.data;
  },
};