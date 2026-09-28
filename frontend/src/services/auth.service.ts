// src/services/auth.service.ts

import { api } from "../context/AuthContext";

export interface RegistroPorAdminResponse {
  message:       string;
  user_id:       number;
  email:         string;
  // false si Brevo falló: la cuenta existe igual, hay que reenviar el link.
  email_enviado: boolean;
}

export const authService = {

  // Auto-registro público (consumidor elige su propia contraseña
  // y verifica su email con PIN)
  registro: async (formData: FormData): Promise<void> => {
    await api.post("/api/users/registro/consumidor/", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  // Registro por admin (ANH/ADMIN) — la cuenta queda PENDIENTE y el
  // consumidor recibe un link de activación para crear su contraseña.
  // Nadie ve la contraseña.
  registroPorAdmin: async (formData: FormData): Promise<RegistroPorAdminResponse> => {
    const res = await api.post(
      "/api/users/registro/consumidor-por-admin/",
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return res.data;
  },

  verificarEmail: async (email: string, pin: string): Promise<void> => {
    await api.post("/api/users/auth/verificar-email/", {
      email,
      codigo_pin: pin,
    });
  },

  recuperarPassword: async (email: string): Promise<void> => {
    await api.post("/api/users/auth/recuperar-password/", { email });
  },

  confirmarRecuperacion: async (
    token: string,
    password: string,
    password2: string,
  ): Promise<void> => {
    await api.post("/api/users/auth/recuperar-password/confirmar/", {
      token,
      password,
      password2,
    });
  },

  reenviarPin: async (email: string): Promise<void> => {
    await api.post("/api/users/auth/reenviar-pin/", { email });
  },

  // Reenvío público del link de activación. El backend responde
  // siempre lo mismo, exista o no la cuenta (anti-enumeración).
  reenviarActivacion: async (email: string): Promise<void> => {
    await api.post("/api/users/auth/reenviar-activacion/", { email });
  },

  cambiarPassword: async (
    password_actual: string,
    password_nuevo: string,
    password_nuevo2: string,
  ): Promise<void> => {
    await api.post("/api/users/auth/cambiar-password/", {
      password_actual,
      password_nuevo,
      password_nuevo2,
    });
  },

  // Cambio forzado cuando requiere_cambio_password=True (contraseña
  // generada por un admin). Sin password_actual — ver
  // CambiarPasswordObligatorioView en el backend.
  cambiarPasswordObligatorio: async (
    password_nuevo: string,
    password_nuevo2: string,
  ): Promise<void> => {
    await api.post("/api/users/auth/cambiar-password-obligatorio/", {
      password_nuevo,
      password_nuevo2,
    });
  },
};