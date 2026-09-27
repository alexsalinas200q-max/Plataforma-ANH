// src/context/AuthContext.tsx

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
} from "react";
import type { ReactNode } from "react";
import axios from "axios";
import type { CupoMensual } from "../types/solicitud.types";

// ------------------------------------------------
// TIPOS
// ------------------------------------------------

// Datos institucionales del usuario autenticado (ADMIN/ANH/ESS),
// tal como los devuelve PerfilFuncionarioSerializer anidado en
// UserSerializer. Es null para CONS. No confundir con
// `PerfilFuncionario` de services/users.service.ts, que trae otra
// forma (estacion_servicio_id/estacion_nombre) pensada para la
// gestión de usuarios por un admin, no para el propio "/me/".
export interface PerfilFuncionarioMe {
  tipo_documento:        "CI" | "PASAPORTE" | "EXTRANJERO";
  numero_documento:      string;
  complemento_documento: string;
  numero_funcionario:    string;
  cargo:                 string;
  unidad_departamento:   string;
  celular:               string;
  estacion_servicio:     number | null;
  fecha_creacion:        string;
}

export interface User {
  id: number;
  email: string;
  nombre_completo: string;
  nombres: string;
  apellido_paterno: string;
  apellido_materno: string;
  tipo_usuario: "ADMIN" | "ANH" | "ESS" | "CONS";
  estado_cuenta: string;
  email_verificado: boolean;
  requiere_cambio_password: boolean;
  date_joined: string;
  access?: string;
  municipio_id: number | null;
  estacion_nombre: string | null;
  perfil_funcionario: PerfilFuncionarioMe | null;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  // Cupo mensual del consumidor autenticado, cacheado acá para no
  // repetir el fetch en cada pantalla que lo necesita (widget,
  // formulario de nueva solicitud). refreshCupo({force:true}) es el
  // punto único de invalidación: post-crear, post-cancelar, y al
  // recibir un 400 de "excede cupo" (por si ANH aprobó algo mientras
  // tanto). Sin force, respeta un TTL de 5 minutos.
  cupo: CupoMensual | null;
  refreshCupo: (opts?: { force?: boolean }) => Promise<CupoMensual | null>;
}

const CUPO_TTL_MS = 5 * 60 * 1000;

// ------------------------------------------------
// GESTION DE TOKEN — memoria + localStorage
// ------------------------------------------------

const TOKEN_KEY = "anh_access_token";

let tokenMemoria: string | null = (() => {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
})();

const setToken = (token: string | null) => {
  tokenMemoria = token;
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else       localStorage.removeItem(TOKEN_KEY);
  } catch { /* modo privado estricto */ }
};

const getToken = () => tokenMemoria;

// ------------------------------------------------
// AXIOS CONFIG
// ------------------------------------------------

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

// REQUEST INTERCEPTOR — inyecta el token en CADA request
// Mas confiable que api.defaults.headers.common en mobile
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

const RUTAS_PUBLICAS = [
  "/login",
  "/registro",
  "/verificar-email",
  "/recuperar-password",
  "/recuperar-password/confirmar",
];

const esRutaPublica = () =>
  RUTAS_PUBLICAS.some(r => window.location.pathname.startsWith(r));

const esUrlExcluida = (url?: string) =>
  !url ||
  url.includes("/auth/login/") ||
  url.includes("/auth/refresh/") ||
  url.includes("/auth/logout/");

// ------------------------------------------------
// RESPONSE INTERCEPTOR — renovar token automáticamente
// ------------------------------------------------

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;

    if (
      error.response?.status === 401 &&
      !original._retry &&
      !esUrlExcluida(original?.url)
    ) {
      original._retry = true;
      try {
        const refreshRes = await axios.post(
          `${API_URL}/api/users/auth/refresh/`,
          {},
          { withCredentials: true }
        );
        if (refreshRes.data?.access) {
          setToken(refreshRes.data.access);
        }
        return api(original);
      } catch {
        setToken(null);
        if (!esRutaPublica()) {
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  }
);

// ------------------------------------------------
// CONTEXTO
// ------------------------------------------------

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user,    setUser]    = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [cupo,    setCupo]    = useState<CupoMensual | null>(null);
  const cupoFetchedAtRef = useRef(0);

  const refreshUser = useCallback(async () => {
    try {
      const res = await api.get("/api/users/me/");
      setUser(res.data);
    } catch {
      setUser(null);
      setToken(null);
    }
  }, []);

  const refreshCupo = useCallback(async (opts?: { force?: boolean }) => {
    if (!user || user.tipo_usuario !== "CONS") {
      setCupo(null);
      return null;
    }
    const fresco = Date.now() - cupoFetchedAtRef.current < CUPO_TTL_MS;
    if (!opts?.force && fresco && cupoFetchedAtRef.current > 0) {
      return cupo;
    }
    try {
      const res = await api.get<CupoMensual>("/api/solicitudes/mi-disponible/");
      setCupo(res.data);
      cupoFetchedAtRef.current = Date.now();
      return res.data;
    } catch {
      return null;
    }
  }, [user, cupo]);

  useEffect(() => {
    if (esRutaPublica()) {
      setLoading(false);
      return;
    }
    refreshUser().finally(() => setLoading(false));
  }, [refreshUser]);

  const login = async (email: string, password: string) => {
    setToken(null);
    try {
      await axios.post(
        `${API_URL}/api/users/auth/logout/`,
        {},
        { withCredentials: true }
      );
    } catch { /* ignorar */ }

    const res = await api.post("/api/users/auth/login/", { email, password });

    if (res.data.access) {
      setToken(res.data.access);
    }

    const meRes = await api.get("/api/users/me/");
    setUser(meRes.data);

    // Cachear cupo al login (best-effort — si falla, MiSolicitud lo
    // vuelve a pedir al montar). No se usa refreshCupo() acá porque
    // leería `user` del closure todavía en null (setUser es async).
    if (meRes.data.tipo_usuario === "CONS") {
      try {
        const cupoRes = await api.get<CupoMensual>("/api/solicitudes/mi-disponible/");
        setCupo(cupoRes.data);
        cupoFetchedAtRef.current = Date.now();
      } catch { /* MiSolicitud reintenta al montar */ }
    }
  };

  const logout = async () => {
    try {
      await axios.post(
        `${API_URL}/api/users/auth/logout/`,
        {},
        { withCredentials: true }
      );
    } catch { /* ignorar */ }
    finally {
      setUser(null);
      setToken(null);
      setCupo(null);
      cupoFetchedAtRef.current = 0;
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        login,
        logout,
        refreshUser,
        cupo,
        refreshCupo,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return ctx;
}