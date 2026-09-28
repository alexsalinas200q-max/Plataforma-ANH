// src/pages/Login.tsx

import { useState, useEffect } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useAuth } from "../context/AuthContext";
import { Flame, Eye, EyeOff, LogIn, AlertCircle, CheckCircle } from "lucide-react";

const schema = z.object({
  email:    z.string().email("Ingresa un email válido"),
  password: z.string().min(1, "Ingresa tu contraseña"),
});

type FormData = z.infer<typeof schema>;

const ALERT_TIMEOUT = 4000;

export default function Login() {
  const { login }               = useAuth();
  const navigate                = useNavigate();
  const [showPass, setShowPass] = useState(false);
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);
  const location                = useLocation();

  // Mensaje de éxito que llega por navigate state (activación de cuenta
  // o cambio de contraseña). Se inicializa desde el state —sin setState
  // dentro de un efecto— y se auto-oculta a los 4s.
  const [exito, setExito] = useState(
    () => (location.state as { mensaje?: string } | null)?.mensaje ?? ""
  );

  useEffect(() => {
    if (!exito) return;
    // Limpiar el state del historial para que un refresh no lo repita.
    navigate(location.pathname, { replace: true, state: null });
    const timer = setTimeout(() => setExito(""), ALERT_TIMEOUT);
    return () => clearTimeout(timer);
  }, [exito, navigate, location.pathname]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    setError("");
    setLoading(true);
    try {
      await login(data.email, data.password);
      navigate("/");
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: { data?: { detail?: string; non_field_errors?: string[]; code?: string } }
      };
      // Solo llega con la contraseña correcta (registro público con el
      // PIN pendiente). Una cuenta pendiente de activación recibe el
      // mismo error que unas credenciales inválidas — anti-enumeración.
      if (axiosErr.response?.data?.code === "email_no_verificado") {
        navigate(`/verificar-email?email=${encodeURIComponent(data.email)}`);
        return;
      }
      const msg =
        axiosErr.response?.data?.detail ||
        axiosErr.response?.data?.non_field_errors?.[0] ||
        "Error al iniciar sesión. Verifica tus credenciales.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-navbar via-[#1f2d3d] to-navbar flex items-center justify-center p-4">

      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-primary/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-primary/5 rounded-full blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        <div className="bg-card rounded-2xl shadow-2xl overflow-hidden">

          {/* HEADER */}
          <div className="bg-navbar px-8 py-8 text-center">
            <div className="w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg">
              <Flame className="w-8 h-8 text-primary-foreground" strokeWidth={2.5} />
            </div>
            <h1 className="text-navbar-foreground text-2xl font-bold tracking-tight">ANH Bolivia</h1>
            <p className="text-navbar-muted text-sm mt-1">Sistema de Gestión de Combustible</p>
          </div>

          {/* FORM */}
          <div className="px-8 py-8">
            <h2 className="text-foreground text-xl font-semibold mb-6 text-center">
              Iniciar sesión
            </h2>

            {exito && (
              <div className="flex items-start gap-3 bg-state-success-bg text-state-success-fg rounded-xl px-4 py-3 mb-5 text-sm">
                <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{exito}</span>
              </div>
            )}

            {error && (
              <div className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 mb-5 text-sm">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">
                  Correo electrónico
                </label>
                <input
                  type="email"
                  autoComplete="email"
                  placeholder="ejemplo@correo.com"
                  {...register("email", { onChange: (e) => { e.target.value = e.target.value.toLowerCase(); } })}
                  className={`w-full px-4 py-2.5 rounded-xl border text-sm transition-colors outline-none ${
                    errors.email
                      ? "border-red-300 bg-red-50 focus:border-red-400 focus:ring-2 focus:ring-red-100"
                      : "border-border bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card"
                  }`}
                />
                {errors.email && (
                  <p className="text-red-500 text-xs mt-1">{errors.email.message}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1.5">
                  Contraseña
                </label>
                <div className="relative">
                  <input
                    type={showPass ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder="••••••••"
                    {...register("password")}
                    className={`w-full px-4 py-2.5 pr-11 rounded-xl border text-sm transition-colors outline-none ${
                      errors.password
                        ? "border-red-300 bg-red-50 focus:border-red-400 focus:ring-2 focus:ring-red-100"
                        : "border-border bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card"
                    }`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {errors.password && (
                  <p className="text-red-500 text-xs mt-1">{errors.password.message}</p>
                )}
              </div>

              <div className="flex items-center justify-between gap-3">
                <Link
                  to="/reenviar-activacion"
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  ¿No recibiste tu enlace de activación?
                </Link>
                <Link
                  to="/recuperar-password"
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  ¿Olvidaste tu contraseña?
                </Link>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover disabled:bg-slate-300 disabled:cursor-not-allowed text-primary-foreground font-semibold py-2.5 rounded-xl transition-colors text-sm"
              >
                {loading
                  ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  : <LogIn className="w-4 h-4" />
                }
                {loading ? "Iniciando sesión..." : "Ingresar"}
              </button>

            </form>

            <p className="text-center text-muted-foreground text-sm mt-6">
              ¿No tienes cuenta?{" "}
              <Link
                to="/registro"
                className="text-foreground font-medium hover:text-primary transition-colors"
              >
                Regístrate aquí
              </Link>
            </p>
          </div>
        </div>

        <p className="text-center text-navbar-muted/60 text-xs mt-4">
           Bolivia v1.0 — Estado Plurinacional de Bolivia
        </p>
      </div>
    </div>
  );
}