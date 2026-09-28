// src/services/users.service.ts

import { api } from "../context/AuthContext";

// ------------------------------------------------
// TIPOS (según respuesta real del backend)
// ------------------------------------------------

export type TipoUsuario  = "ANH" | "ESS" | "ADMIN" | "CONSUMIDOR";

// Coincide con User.EstadoCuenta del backend (users/models.py).
export type EstadoCuenta = "PENDIENTE" | "ACTIVO" | "SUSPENDIDO";

// Coincide con PerfilFuncionario.TipoDocumento del backend.
// Ojo: los funcionarios NO usan "CIE" (eso es de DocumentoIdentidad,
// el modelo de consumidores).
export type TipoDocumento = "CI" | "PASAPORTE" | "EXTRANJERO";

export interface PerfilFuncionario {
  id:                  number;
  cargo:               string;
  unidad_departamento: string;
  numero_funcionario:  string;
  numero_documento:    string;
  tipo_documento:      TipoDocumento;
  celular:             string;
  estacion_servicio_id: number | null;
  estacion_nombre:      string | null;
}

export interface UserFuncionario {
  id:                number;
  email:             string;
  nombres:           string;
  apellido_paterno:  string;
  apellido_materno:  string;
  nombre_completo:   string;
  tipo_usuario:      TipoUsuario;
  estado_cuenta:     EstadoCuenta;
  email_verificado:  boolean;
  date_joined:       string;
  perfil:            PerfilFuncionario | null;
}

// Payload para crear.
// El backend crea un PerfilFuncionario para TODO funcionario
// (ADMIN incluido), así que los campos de perfil son obligatorios
// salvo complemento y celular.
export interface CrearFuncionarioPayload {
  email:            string;
  nombres:          string;
  apellido_paterno: string;
  apellido_materno?: string;
  tipo_usuario:     "ANH" | "ESS" | "ADMIN";

  cargo:                string;
  unidad_departamento:  string;
  numero_funcionario:   string;
  numero_documento:     string;
  tipo_documento:       TipoDocumento;
  celular?:             string;
  complemento_documento?: string;

  // Solo para ESS
  estacion_servicio?: number;
}

// Ni el alta ni el reset devuelven contraseña: el usuario recibe un
// link por email. email_enviado=false si el envío falló.
export interface CrearFuncionarioResponse {
  detail:        string;
  user_id:       number;
  email:         string;
  tipo_usuario:  string;
  email_enviado: boolean;
}

export interface EnlaceEnviadoResponse {
  detail:        string;
  email:         string;
  email_enviado: boolean;
}

// Payload para editar
export interface EditarFuncionarioPayload {
  nombres?:          string;
  apellido_paterno?: string;
  apellido_materno?: string;
  cargo?:               string;
  unidad_departamento?: string;
  numero_funcionario?:  string;
  numero_documento?:    string;
  tipo_documento?:      TipoDocumento;
  celular?:             string;
  estacion_servicio_id?: number | null;
}

// ------------------------------------------------
// SERVICE
// ------------------------------------------------

export const usersService = {

  // Retorna un array plano (el backend NO pagina este endpoint)
  listar: async (params?: Record<string, string>): Promise<UserFuncionario[]> => {
    const res = await api.get("/api/users/funcionarios/", { params });
    const data = res.data;
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.results)) return data.results;
    return [];
  },

  detalle: async (id: number): Promise<UserFuncionario> => {
    const res = await api.get(`/api/users/funcionarios/${id}/`);
    return res.data;
  },

  crear: async (payload: CrearFuncionarioPayload): Promise<CrearFuncionarioResponse> => {
    const res = await api.post("/api/users/funcionarios/crear/", payload);
    return res.data;
  },

  actualizar: async (id: number, payload: EditarFuncionarioPayload): Promise<{ detail: string }> => {
    const res = await api.patch(`/api/users/funcionarios/${id}/`, payload);
    return res.data;
  },

  cambiarEstado: async (id: number, estado: EstadoCuenta): Promise<UserFuncionario> => {
    const res = await api.post(`/api/users/funcionarios/${id}/cambiar-estado/`, {
      estado_cuenta: estado,
    });
    return res.data;
  },

  resetearPassword: async (id: number): Promise<EnlaceEnviadoResponse> => {
    const res = await api.post(`/api/users/funcionarios/${id}/resetear-password/`);
    return res.data;
  },

  // {id} es el id de User (no de perfil). ADMIN: cualquier usuario;
  // ANH: solo consumidores (403 si no).
  reenviarActivacion: async (id: number): Promise<EnlaceEnviadoResponse> => {
    const res = await api.post(`/api/users/usuarios/${id}/reenviar-activacion/`);
    return res.data;
  },
};