// src/services/consumidores.service.ts

import { api } from "../context/AuthContext";
import type { ConsumidorPerfil, ConsumidorListItem } from "../types/consumidor.types";

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

  // Búsqueda por nombre, apellido, email o N° de documento (search del backend).
  buscar: async (texto: string): Promise<ConsumidorListItem[]> => {
    const res = await api.get("/api/consumidores/", { params: { search: texto } });
    return res.data.results ?? res.data;
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
