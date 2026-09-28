// src/pages/RecuperarPassword.tsx

import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { authService } from "../services/auth.service";
import { Flame, Mail, ArrowLeft, CheckCircle, AlertCircle } from "lucide-react";

const schema = z.object({
  email: z.string().email("Ingresa un email válido"),
});

type FormData = z.infer<typeof schema>;

// También sirve de formulario público para reenviar el link de
// activación (cuentas creadas por un administrador). En ambos modos el
// backend responde siempre lo mismo, exista o no el email.
type Modo = "recuperacion" | "activacion";

const textos: Record<Modo, {
  subtitulo:   string;
  titulo:      string;
  descripcion: string;
  exito:       string;
}> = {
  recuperacion: {
    subtitulo:   "Recuperar contraseña",
    titulo:      "¿Olvidaste tu contraseña?",
    descripcion: "Ingresa tu correo y te enviaremos un enlace para restablecerla.",
    exito:       "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña en los próximos minutos.",
  },
  activacion: {
    subtitulo:   "Activar cuenta",
    titulo:      "¿No recibiste tu enlace de activación?",
    descripcion: "Ingresa el correo con el que te registraron y te enviaremos un nuevo enlace para activar tu cuenta.",
    exito:       "Si el correo corresponde a una cuenta pendiente de activación, recibirás un nuevo enlace en los próximos minutos.",
  },
};

interface Props {
  modo?: Modo;
}

export default function RecuperarPassword({ modo = "recuperacion" }: Props) {
  const t = textos[modo];
  const [enviado,  setEnviado]  = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    setLoading(true);
    setError("");
    try {
      if (modo === "activacion") {
        await authService.reenviarActivacion(data.email);
      } else {
        await authService.recuperarPassword(data.email);
      }
      setEnviado(true);
    } catch {
      setError("Error al procesar la solicitud. Intenta nuevamente.");
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
            <h1 className="text-navbar-foreground text-2xl font-bold">ANH Bolivia</h1>
            <p className="text-navbar-muted text-sm mt-1">{t.subtitulo}</p>
          </div>

          <div className="px-8 py-8">

            {/* ÉXITO */}
            {enviado ? (
              <div className="text-center space-y-4">
                <div className="w-16 h-16 bg-state-success-bg rounded-full flex items-center justify-center mx-auto">
                  <CheckCircle className="w-8 h-8 text-state-success-fg" />
                </div>
                <h2 className="text-foreground text-xl font-semibold">
                  Revisa tu correo
                </h2>
                <p className="text-muted-foreground text-sm">
                  {t.exito}
                </p>
                <div className="bg-primary/10 rounded-xl px-4 py-3 text-xs text-primary">
                  Revisa también tu carpeta de spam o correo no deseado.
                </div>
                <Link
                  to="/login"
                  className="flex items-center justify-center gap-2 w-full px-5 py-2.5 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:bg-primary-hover transition-colors mt-4"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Volver al login
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
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                      <input
                        type="email"
                        autoComplete="email"
                        placeholder="ejemplo@correo.com"
                        {...register("email", { onChange: (e) => { e.target.value = e.target.value.toLowerCase(); } })}
                        className={`w-full pl-10 pr-4 py-2.5 rounded-xl border text-sm transition-colors outline-none ${
                          errors.email
                            ? "border-red-300 bg-red-50 focus:border-red-400 focus:ring-2 focus:ring-red-100"
                            : "border-border bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card"
                        }`}
                      />
                    </div>
                    {errors.email && (
                      <p className="text-red-500 text-xs mt-1">{errors.email.message}</p>
                    )}
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover disabled:bg-slate-300 disabled:cursor-not-allowed text-primary-foreground font-semibold py-2.5 rounded-xl transition-colors text-sm"
                  >
                    {loading
                      ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      : <Mail className="w-4 h-4" />
                    }
                    {loading ? "Enviando..." : "Enviar enlace"}
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