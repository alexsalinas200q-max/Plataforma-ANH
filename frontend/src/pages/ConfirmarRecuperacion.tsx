// src/pages/ConfirmarRecuperacion.tsx

import { passwordSeguroSchema, PASSWORD_HELP_TEXT } from "../utils/passwordSchema";
import { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { authService } from "../services/auth.service";
import { Flame, Eye, EyeOff, CheckCircle, AlertCircle, ArrowLeft } from "lucide-react";

const schema = z.object({
  password:  passwordSeguroSchema,
  password2: z.string().min(1, "Repite la contraseña"),
}).refine(d => d.password === d.password2, {
  message: "Las contraseñas no coinciden",
  path: ["password2"],
});

type FormData = z.infer<typeof schema>;

// La misma pantalla sirve para recuperar la contraseña y para activar
// una cuenta creada por un administrador: ambos flujos usan el mismo
// token RECUP y el mismo endpoint (el backend activa la cuenta si
// está PENDIENTE). Solo cambian los textos y a dónde se pide un
// enlace nuevo.
type Modo = "recuperacion" | "activacion";

const textos: Record<Modo, {
  subtitulo:     string;
  titulo:        string;
  descripcion:   string;
  boton:         string;
  guardando:     string;
  errorDefault:  string;
  sinToken:      string;
  exitoTitulo:   string;
  exitoTexto:    string;
  rutaNuevoLink: string;
  textoNuevoLink: string;
}> = {
  recuperacion: {
    subtitulo:      "Nueva contraseña",
    titulo:         "Crea tu nueva contraseña",
    descripcion:    "Ingresa y confirma tu nueva contraseña.",
    boton:          "Cambiar contraseña",
    guardando:      "Guardando...",
    errorDefault:   "Error al cambiar la contraseña. El enlace puede haber expirado.",
    sinToken:       "Enlace inválido. Solicita un nuevo enlace de recuperación.",
    exitoTitulo:    "¡Contraseña actualizada!",
    exitoTexto:     "Tu contraseña fue cambiada exitosamente. Serás redirigido al login en unos segundos...",
    rutaNuevoLink:  "/recuperar-password",
    textoNuevoLink: "Solicitar un nuevo enlace",
  },
  activacion: {
    subtitulo:      "Activar cuenta",
    titulo:         "Bienvenido",
    descripcion:    "Crea tu contraseña para activar tu cuenta.",
    boton:          "Activar cuenta",
    guardando:      "Activando...",
    errorDefault:   "No se pudo activar la cuenta. El enlace puede haber expirado.",
    sinToken:       "Enlace inválido. Solicita un nuevo enlace de activación.",
    exitoTitulo:    "¡Cuenta activada!",
    exitoTexto:     "Tu cuenta está activa. Serás redirigido al login en unos segundos...",
    rutaNuevoLink:  "/reenviar-activacion",
    textoNuevoLink: "Solicitar un nuevo enlace de activación",
  },
};

interface Props {
  modo?: Modo;
}

export default function ConfirmarRecuperacion({ modo = "recuperacion" }: Props) {
  const t = textos[modo];
  const navigate                    = useNavigate();
  const [searchParams]              = useSearchParams();
  const token                       = searchParams.get("token") ?? "";

  const [showPass,  setShowPass]    = useState(false);
  const [showPass2, setShowPass2]   = useState(false);
  const [loading,   setLoading]     = useState(false);
  const [error,     setError]       = useState("");
  const [exito,     setExito]       = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    if (!token) {
      setError(t.sinToken);
      return;
    }
    setLoading(true);
    setError("");
    try {
      await authService.confirmarRecuperacion(token, data.password, data.password2);
      setExito(true);
      setTimeout(() => navigate("/login", {
        state: { mensaje: modo === "activacion"
          ? "Cuenta activada. Ya puedes iniciar sesión."
          : "Contraseña actualizada. Ya puedes iniciar sesión." },
      }), 3000);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string; non_field_errors?: string[] } } };
      const msg =
        e.response?.data?.detail ||
        e.response?.data?.non_field_errors?.[0] ||
        t.errorDefault;
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const inputCls = (hasError: boolean) =>
    `w-full px-4 py-2.5 rounded-xl border text-sm transition-colors outline-none ${
      hasError
        ? "border-red-300 bg-red-50 focus:border-red-400 focus:ring-2 focus:ring-red-100"
        : "border-border bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card"
    }`;

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
            <h1 className="text-navbar-foreground text-2xl font-bold">ANH Bolivia</h1>
            <p className="text-navbar-muted text-sm mt-1">{t.subtitulo}</p>
          </div>

          <div className="px-8 py-8">

            {/* ÉXITO */}
            {exito ? (
              <div className="text-center space-y-4">
                <div className="w-16 h-16 bg-state-success-bg rounded-full flex items-center justify-center mx-auto">
                  <CheckCircle className="w-8 h-8 text-state-success-fg" />
                </div>
                <h2 className="text-foreground text-xl font-semibold">
                  {t.exitoTitulo}
                </h2>
                <p className="text-muted-foreground text-sm">
                  {t.exitoTexto}
                </p>
                <Link
                  to="/login"
                  className="flex items-center justify-center gap-2 w-full px-5 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary-hover transition-colors"
                >
                  Ir al login
                </Link>
              </div>
            ) : (
              <>
                <h2 className="text-foreground text-xl font-semibold mb-2 text-center">
                  {t.titulo}
                </h2>
                <p className="text-muted-foreground text-sm text-center mb-6">
                  {t.descripcion}
                </p>

                {!token && (
                  <div className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 mb-5 text-sm">
                    <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{t.sinToken}</span>
                  </div>
                )}

                {error && (
                  <div className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 mb-5 text-sm">
                    <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>
                      {error}{" "}
                      <Link to={t.rutaNuevoLink} className="font-medium underline">
                        {t.textoNuevoLink}
                      </Link>
                    </span>
                  </div>
                )}

                <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">
                      Nueva contraseña
                    </label>
                    <div className="relative">
                      <input
                        type={showPass ? "text" : "password"}
                        placeholder="Mínimo 8 caracteres"
                        {...register("password")}
                        className={inputCls(!!errors.password) + " pr-11"}
                      />
                      <p className="text-xs text-muted-foreground mt-1">{PASSWORD_HELP_TEXT}</p>

                      <button
                        type="button"
                        onClick={() => setShowPass(!showPass)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    {errors.password && (
                      <p className="text-red-500 text-xs mt-1">{errors.password.message}</p>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1.5">
                      Confirmar contraseña
                    </label>
                    <div className="relative">
                      <input
                        type={showPass2 ? "text" : "password"}
                        placeholder="Repite la contraseña"
                        {...register("password2")}
                        className={inputCls(!!errors.password2) + " pr-11"}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPass2(!showPass2)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showPass2 ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    {errors.password2 && (
                      <p className="text-red-500 text-xs mt-1">{errors.password2.message}</p>
                    )}
                  </div>

                  <button
                    type="submit"
                    disabled={loading || !token}
                    className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover disabled:bg-slate-300 disabled:cursor-not-allowed text-primary-foreground font-semibold py-2.5 rounded-xl transition-colors text-sm"
                  >
                    {loading
                      ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      : <CheckCircle className="w-4 h-4" />
                    }
                    {loading ? t.guardando : t.boton}
                  </button>
                </form>

                <p className="text-center text-muted-foreground text-sm mt-6">
                  <Link to="/login" className="flex items-center justify-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors">
                    <ArrowLeft className="w-3.5 h-3.5" />
                    Volver al login
                  </Link>
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}