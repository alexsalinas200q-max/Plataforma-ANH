// src/pages/admin/RegistrarConsumidor.tsx

import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import Layout from "../../components/Layout";
import { Card, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { Modal } from "../../components/ui/Modal";
import { Stepper } from "../../components/ui/Stepper";
import { authService } from "../../services/auth.service";
import { usersService } from "../../services/users.service";
import { catalogosService } from "../../services/catalogos.service";
import { ACTIVIDADES, TIPOS_DOCUMENTO } from "../../utils/constants";
import type { Departamento, Provincia, Municipio } from "../../types/consumidor.types";
import {
  UserPlus, ArrowLeft, ArrowRight, CheckCircle,
  ImagePlus, X, Info, Mail, Send,
} from "lucide-react";

// ------------------------------------------------
// SCHEMA
// ------------------------------------------------

const schema = z.object({
  // Paso 1: Datos personales
  email:            z.string().email("Email inválido"),
  nombres:          z.string().min(2, "Mínimo 2 caracteres"),
  apellido_paterno: z.string().min(2, "Mínimo 2 caracteres"),
  apellido_materno: z.string().optional(),
  celular:          z.string().min(7, "Mínimo 7 dígitos").regex(/^\d+$/, "Solo se permiten números"),
  fecha_nacimiento: z.string().min(1, "Fecha requerida"),

  // Paso 2: Ubicación
  departamento: z.number().int().positive("Selecciona un departamento"),
  provincia:    z.number().int().positive("Selecciona una provincia"),
  municipio:    z.number().int().positive("Selecciona un municipio"),
  direccion:    z.string().optional(),
  actividad:    z.string().min(1, "Selecciona la actividad económica"),

  // Paso 3: Documento
  // Las tres imágenes son obligatorias: el backend las exige
  // (ImageField sin required=False en RegistroConsumidorPorAdminSerializer).
  tipo_documento:        z.enum(["CI", "CIE"]),
  numero_documento:      z.string()
                          .min(5, "Mínimo 5 dígitos")
                          .regex(/^\d+$/, "Solo se permiten números"),
  complemento_documento: z.string().optional(),
  documento_anverso:     z.instanceof(FileList).refine(f => f.length > 0, "Requerido"),
  documento_reverso:     z.instanceof(FileList).refine(f => f.length > 0, "Requerido"),
  foto_sosteniendo:      z.instanceof(FileList).refine(f => f.length > 0, "Requerido"),
});

type FormData = z.infer<typeof schema>;

// ------------------------------------------------
// STEPS
// ------------------------------------------------

const STEPS = [
  { label: "Datos personales" },
  { label: "Ubicación y consumo" },
  { label: "Documento" },
  { label: "Revisión" },
];

// Campos de cada paso — para validar antes de avanzar
const CAMPOS_PASO: Record<number, (keyof FormData)[]> = {
  1: ["email", "nombres", "apellido_paterno", "apellido_materno", "celular", "fecha_nacimiento"],
  2: ["departamento", "provincia", "municipio", "direccion", "actividad"],
  3: ["tipo_documento", "numero_documento", "documento_anverso", "documento_reverso", "foto_sosteniendo"],
};

// ------------------------------------------------
// COMPONENTE PRINCIPAL
// ------------------------------------------------

export default function RegistrarConsumidor() {
  const navigate = useNavigate();
  const [paso,       setPaso]       = useState(1);
  const [enviando,   setEnviando]   = useState(false);
  const [errorForm,  setErrorForm]  = useState("");

  // Datos de éxito para el modal. No hay contraseña: el consumidor
  // recibe un link de activación. emailEnviado=false si el envío falló.
  const [exitoData, setExitoData] = useState<{
    nombre:       string;
    email:        string;
    emailEnviado: boolean;
    userId:       number;
  } | null>(null);
  const [reenviando, setReenviando] = useState(false);

  const {
    register, handleSubmit, watch, setValue, trigger,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: "", nombres: "", apellido_paterno: "", apellido_materno: "",
      celular: "", fecha_nacimiento: "",
      departamento: 0, provincia: 0, municipio: 0, direccion: "",
      actividad: "",
      tipo_documento: "CI", numero_documento: "", complemento_documento: "",
    },
  });

  const [deptos, setDeptos] = useState<Departamento[]>([]);
  const [provs,  setProvs]  = useState<Provincia[]>([]);
  const [munis,  setMunis]  = useState<Municipio[]>([]);
  const [loadCat, setLoadCat] = useState(false);

  const watchDepto  = watch("departamento");
  const watchProv   = watch("provincia");
  const watchAnv    = watch("documento_anverso");
  const watchRev    = watch("documento_reverso");
  const watchFoto   = watch("foto_sosteniendo");
  const values      = watch();

  useEffect(() => {
    catalogosService.getDepartamentos().then(setDeptos).catch(() => {});
  }, []);

  const onDeptoChange = async (deptoId: number) => {
    setValue("departamento", deptoId);
    setValue("provincia", 0);
    setValue("municipio", 0);
    setProvs([]); setMunis([]);
    if (!deptoId) return;
    setLoadCat(true);
    try { setProvs(await catalogosService.getProvincias(deptoId)); }
    finally { setLoadCat(false); }
  };

  const onProvChange = async (provId: number) => {
    setValue("provincia", provId);
    setValue("municipio", 0);
    setMunis([]);
    if (!provId) return;
    setLoadCat(true);
    try { setMunis(await catalogosService.getMunicipios(provId)); }
    finally { setLoadCat(false); }
  };

  // ------------------------------------------------
  // NAVEGACIÓN ENTRE PASOS
  // ------------------------------------------------

  const irSiguiente = async () => {
    const camposActuales = CAMPOS_PASO[paso];
    const ok = await trigger(camposActuales);
    if (ok) {
      setErrorForm("");
      setPaso(p => p + 1);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  const irAnterior = () => {
    setErrorForm("");
    setPaso(p => p - 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const irAPaso = (n: number) => {
    setErrorForm("");
    setPaso(n);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // ------------------------------------------------
  // SUBMIT FINAL — payload plano al endpoint por-admin
  // ------------------------------------------------

  const onSubmit = async (data: FormData) => {
    setEnviando(true);
    setErrorForm("");
    try {
      const fd = new FormData();
      fd.append("email",              data.email);
      fd.append("nombres",            data.nombres);
      fd.append("apellido_paterno",   data.apellido_paterno);
      fd.append("apellido_materno",   data.apellido_materno ?? "");
      fd.append("celular",            data.celular);
      fd.append("fecha_nacimiento",   data.fecha_nacimiento);
      fd.append("departamento",       String(data.departamento));
      fd.append("provincia",          String(data.provincia));
      fd.append("municipio",          String(data.municipio));
      fd.append("direccion",          data.direccion ?? "");
      fd.append("actividad",          data.actividad);
      fd.append("tipo_documento",     data.tipo_documento);
      fd.append("numero_documento",   data.numero_documento);
      if (data.complemento_documento) {
        fd.append("complemento_documento", data.complemento_documento);
      }
      fd.append("anverso",          data.documento_anverso[0]);
      fd.append("reverso",          data.documento_reverso[0]);
      fd.append("foto_sosteniendo", data.foto_sosteniendo[0]);

      const res = await authService.registroPorAdmin(fd);
      setExitoData({
        nombre:   `${data.nombres} ${data.apellido_paterno}`,
        email:    res.email,
        emailEnviado: res.email_enviado,
        userId:       res.user_id,
      });
    } catch (err: unknown) {
      // El backend puede devolver un string plano o un objeto de errores
      // por campo. Si es string, iterarlo con Object.entries lo partiría
      // carácter por carácter, así que se distingue el tipo primero.
      const e = err as { response?: { data?: unknown } };
      const d = e.response?.data;
      let msg = "Error al registrar el consumidor.";

      if (typeof d === "string") {
        msg = d;
      } else if (d && typeof d === "object") {
        const entries = Object.entries(d as Record<string, unknown>);
        if (entries.length > 0) {
          msg = entries
            .map(([k, v]) => `${k}: ${Array.isArray(v) ? v[0] : String(v)}`)
            .join(" | ");
        }
      }

      setErrorForm(msg);
    } finally {
      setEnviando(false);
    }
  };

  const reenviarActivacion = async () => {
    if (!exitoData) return;
    setReenviando(true);
    try {
      const res = await usersService.reenviarActivacion(exitoData.userId);
      setExitoData({ ...exitoData, emailEnviado: res.email_enviado });
    } catch {
      setExitoData({ ...exitoData, emailEnviado: false });
    } finally { setReenviando(false); }
  };

  const inputCls  = "w-full px-4 py-2.5 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none";
  const selectCls = inputCls + " disabled:opacity-50";
  const errorCls  = "text-red-500 text-xs mt-1";

  const nombreCompleto = `${values.nombres} ${values.apellido_paterno} ${values.apellido_materno ?? ""}`.trim();
  const ubicacionLabel = [
    deptos.find(d => d.id === values.departamento)?.nombre,
    provs.find(p => p.id === values.provincia)?.nombre,
    munis.find(m => m.id === values.municipio)?.nombre,
  ].filter(Boolean).join(" · ") || "—";

  return (
    <Layout>
      <div className="max-w-3xl mx-auto space-y-5">

        {/* HEADER */}
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-navbar rounded-xl flex items-center justify-center">
                <UserPlus className="w-5 h-5 text-navbar-foreground" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-foreground">Registrar Consumidor</h1>
                <p className="text-muted-foreground text-sm">Completa los datos en {STEPS.length} pasos</p>
              </div>
            </div>
          </div>
        </div>

        {/* STEPPER */}
        <Card>
          <div className="px-5 py-3 border-b border-border">
            <Stepper steps={STEPS} currentStep={paso} />
          </div>

          {/*
            El submit del formulario se bloquea a propósito: el envío real
            se dispara solo desde el botón "Registrar consumidor" del paso 4.
            Así, presionar Enter en cualquier input no crea el consumidor
            a medio llenar.
          */}
          <form onSubmit={e => e.preventDefault()}>

            {/* PASO 1 — DATOS PERSONALES */}
            {paso === 1 && (
              <CardBody className="space-y-4">
                <h2 className="font-semibold text-foreground">Datos personales del consumidor</h2>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Nombres *</label>
                    <input {...register("nombres")} className={inputCls} />
                    {errors.nombres && <p className={errorCls}>{errors.nombres.message}</p>}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Apellido paterno *</label>
                    <input {...register("apellido_paterno")} className={inputCls} />
                    {errors.apellido_paterno && <p className={errorCls}>{errors.apellido_paterno.message}</p>}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Apellido materno</label>
                    <input {...register("apellido_materno")} className={inputCls} />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Fecha de nacimiento *</label>
                    <input type="date" {...register("fecha_nacimiento")} className={inputCls} />
                    {errors.fecha_nacimiento && <p className={errorCls}>{errors.fecha_nacimiento.message}</p>}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Email *</label>
                    <input type="email" {...register("email", { onChange: e => { e.target.value = e.target.value.toLowerCase(); } })} className={inputCls} />
                    {errors.email && <p className={errorCls}>{errors.email.message}</p>}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Celular *</label>
                    <input
                      {...register("celular")}
                      className={inputCls}
                      inputMode="numeric"
                      placeholder="Ej: 78123456"
                      onInput={e => {
                        const el = e.target as HTMLInputElement;
                        el.value = el.value.replace(/\D/g, "");
                      }}
                    />
                    {errors.celular && <p className={errorCls}>{errors.celular.message}</p>}
                  </div>
                </div>
              </CardBody>
            )}

            {/* PASO 2 — UBICACIÓN Y CONSUMO */}
            {paso === 2 && (
              <CardBody className="space-y-4">
                <h2 className="font-semibold text-foreground">Ubicación y actividad económica</h2>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Departamento *</label>
                    <select value={watchDepto || 0} onChange={e => onDeptoChange(Number(e.target.value))} className={selectCls}>
                      <option value={0}>Seleccionar...</option>
                      {deptos.map(d => <option key={d.id} value={d.id}>{d.nombre}</option>)}
                    </select>
                    {errors.departamento && <p className={errorCls}>{errors.departamento.message}</p>}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Provincia *</label>
                    <select value={watchProv || 0} onChange={e => onProvChange(Number(e.target.value))}
                      disabled={!watchDepto || loadCat} className={selectCls}>
                      <option value={0}>{loadCat ? "Cargando..." : "Seleccionar..."}</option>
                      {provs.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                    </select>
                    {errors.provincia && <p className={errorCls}>{errors.provincia.message}</p>}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Municipio *</label>
                    <select {...register("municipio", { valueAsNumber: true })}
                      disabled={!watchProv || loadCat} className={selectCls}>
                      <option value={0}>{loadCat ? "Cargando..." : "Seleccionar..."}</option>
                      {munis.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}
                    </select>
                    {errors.municipio && <p className={errorCls}>{errors.municipio.message}</p>}
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Dirección (opcional)</label>
                  <input {...register("direccion")} className={inputCls} placeholder="Calle, número, referencia..." />
                </div>

                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Actividad económica *</label>
                  <select {...register("actividad")} className={inputCls}>
                    <option value="">Seleccionar...</option>
                    {Object.entries(ACTIVIDADES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  {errors.actividad && <p className={errorCls}>{errors.actividad.message}</p>}
                </div>
              </CardBody>
            )}

            {/* PASO 3 — DOCUMENTO */}
            {paso === 3 && (
              <CardBody className="space-y-4">
                <h2 className="font-semibold text-foreground">Documento de identidad</h2>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Tipo *</label>
                    <select {...register("tipo_documento")} className={inputCls}>
                      {TIPOS_DOCUMENTO.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Número *</label>
                    <input
                      {...register("numero_documento")}
                      className={inputCls}
                      inputMode="numeric"
                      placeholder="Ej: 12345678"
                      onInput={e => {
                        // Bloquea cualquier carácter que no sea dígito
                        const el = e.target as HTMLInputElement;
                        el.value = el.value.replace(/\D/g, "");
                      }}
                    />
                    {errors.numero_documento && <p className={errorCls}>{errors.numero_documento.message}</p>}
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">Complemento</label>
                    <input {...register("complemento_documento")} className={inputCls} placeholder="Opcional" />
                  </div>
                </div>

                <div className="bg-primary/5 border border-primary/20 rounded-xl px-4 py-3 flex items-start gap-2">
                  <Info className="w-4 h-4 text-primary shrink-0 mt-0.5" />
                  <p className="text-xs text-primary">
                    Sube fotos claras y legibles del documento. Las <strong>tres imágenes son obligatorias</strong>.
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <UploadCard
                    label="Anverso"
                    required
                    register={register("documento_anverso")}
                    files={watchAnv}
                    onClear={() => setValue("documento_anverso", null as unknown as FileList)}
                    error={errors.documento_anverso?.message as string | undefined}
                  />
                  <UploadCard
                    label="Reverso"
                    required
                    register={register("documento_reverso")}
                    files={watchRev}
                    onClear={() => setValue("documento_reverso", null as unknown as FileList)}
                    error={errors.documento_reverso?.message as string | undefined}
                  />
                  <UploadCard
                    label="Con documento en mano"
                    required
                    register={register("foto_sosteniendo")}
                    files={watchFoto}
                    onClear={() => setValue("foto_sosteniendo", null as unknown as FileList)}
                    error={errors.foto_sosteniendo?.message as string | undefined}
                  />
                </div>
              </CardBody>
            )}

            {/* PASO 4 — REVISIÓN */}
            {paso === 4 && (
              <CardBody className="space-y-4">
                <h2 className="font-semibold text-foreground">Revisar y confirmar</h2>
                <p className="text-sm text-muted-foreground">
                  Verifica que los datos sean correctos antes de crear el consumidor.
                </p>

                {errorForm && <Alert type="error" message={errorForm} />}

                <ReviewSection
                  title="Datos personales"
                  onEdit={() => irAPaso(1)}
                  items={[
                    ["Nombre completo",     nombreCompleto || "—"],
                    ["Email",               values.email || "—"],
                    ["Celular",             values.celular || "—"],
                    ["Fecha de nacimiento", values.fecha_nacimiento || "—"],
                  ]}
                />

                <ReviewSection
                  title="Ubicación y consumo"
                  onEdit={() => irAPaso(2)}
                  items={[
                    ["Ubicación", ubicacionLabel],
                    ["Dirección", values.direccion || "—"],
                    ["Actividad", ACTIVIDADES[values.actividad] ?? "—"],
                  ]}
                />

                <ReviewSection
                  title="Documento de identidad"
                  onEdit={() => irAPaso(3)}
                  items={[
                    ["Tipo",     `${values.tipo_documento} — ${values.numero_documento || "—"}${values.complemento_documento ? " " + values.complemento_documento : ""}`],
                    ["Anverso",     watchAnv?.[0]  ? "✓ Cargado" : "—"],
                    ["Reverso",     watchRev?.[0]  ? "✓ Cargado" : "—"],
                    ["Sosteniendo", watchFoto?.[0] ? "✓ Cargado" : "—"],
                  ]}
                />
              </CardBody>
            )}

            {/*
              NAVEGACIÓN ENTRE PASOS

              Los `key` distintos son necesarios: sin ellos React reutiliza
              el mismo nodo DOM entre "Siguiente" y "Registrar consumidor"
              (ocupan la misma posición en el árbol), y al pasar del paso 3
              al 4 el navegador terminaba disparando el submit con el
              atributo ya actualizado — registrando sin que nadie pulsara
              el botón final.
            */}
            <div className="px-5 py-4 border-t border-border flex items-center justify-between">
              {paso > 1 ? (
                <Button variant="outline" type="button" icon={<ArrowLeft className="w-4 h-4" />} onClick={irAnterior}>
                  Anterior
                </Button>
              ) : (
                <Button variant="outline" type="button" onClick={() => navigate(-1)}>
                  Cancelar
                </Button>
              )}

              <span className="text-xs text-muted-foreground">Paso {paso} de {STEPS.length}</span>

              {paso < STEPS.length ? (
                <Button
                  key="btn-siguiente"
                  variant="primary"
                  type="button"
                  onClick={irSiguiente}
                >
                  Siguiente
                  <ArrowRight className="w-4 h-4" />
                </Button>
              ) : (
                <Button
                  key="btn-registrar"
                  variant="primary"
                  type="button"
                  icon={<CheckCircle className="w-4 h-4" />}
                  loading={enviando}
                  onClick={handleSubmit(onSubmit)}
                >
                  Registrar consumidor
                </Button>
              )}
            </div>
          </form>
        </Card>
      </div>

      {/* MODAL DE ÉXITO (enlace de activación enviado) */}
      <Modal open={!!exitoData} onClose={() => {}} title="" size="md">
        {exitoData && (
          <div className="py-2">
            <div className="text-center mb-4">
              <div className="w-14 h-14 rounded-full bg-state-success-bg flex items-center justify-center mx-auto mb-3">
                <CheckCircle className="w-7 h-7 text-state-success-fg" />
              </div>
              <h3 className="font-semibold text-foreground mb-1">Consumidor registrado</h3>
              <p className="text-sm text-muted-foreground">
                <strong>{exitoData.nombre}</strong> fue registrado correctamente.
              </p>
            </div>

            {exitoData.emailEnviado ? (
              <div className="flex items-start gap-3 bg-background border border-border rounded-xl px-4 py-3">
                <Mail className="w-4 h-4 text-state-success-fg shrink-0 mt-0.5" />
                <p className="text-sm text-foreground">
                  Se envió un enlace de activación a <strong>{exitoData.email}</strong>.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <Alert
                  type="warning"
                  message={`El consumidor se registró, pero no se pudo enviar el email de activación a ${exitoData.email}. Reenvía el enlace.`}
                />
                <Button variant="outline" icon={<Send className="w-4 h-4" />}
                  loading={reenviando} onClick={reenviarActivacion} className="w-full">
                  Reenviar enlace
                </Button>
              </div>
            )}

            <div className="flex items-start gap-2 text-xs text-muted-foreground mt-3">
              <Info className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                El consumidor debe abrir el enlace y crear su contraseña para activar
                la cuenta. El enlace vence en 72 horas; si vence, puede pedir uno
                nuevo desde la pantalla de inicio de sesión.
              </span>
            </div>

            <div className="flex flex-col gap-2 mt-5">
              <Button variant="primary" onClick={() => navigate("/anh/consumidores")}>
                Ir al listado
              </Button>
              <Button variant="outline" onClick={() => window.location.reload()}>
                Registrar otro consumidor
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </Layout>
  );
}

// ------------------------------------------------
// SUB-COMPONENTE: UPLOAD CARD CON PREVIEW
// ------------------------------------------------

interface UploadCardProps {
  label:     string;
  required?: boolean;
  register:  ReturnType<ReturnType<typeof useForm<FormData>>["register"]>;
  files:     FileList | undefined;
  onClear:   () => void;
  error?:    string;
}

function UploadCard({ label, required, register, files, onClear, error }: UploadCardProps) {
  const hasFile = files && files.length > 0;
  const previewUrl = hasFile ? URL.createObjectURL(files[0]) : null;

  return (
    <div>
      <div className={`
        relative rounded-xl border-2 overflow-hidden transition-colors
        ${hasFile ? "border-primary" : error ? "border-red-300" : "border-dashed border-border hover:border-primary/50"}
      `}>
        {hasFile && previewUrl ? (
          <>
            <img src={previewUrl} alt={label} className="w-full h-24 object-cover" />
            <button
              type="button"
              onClick={onClear}
              className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80 transition-colors"
              title="Quitar imagen"
            >
              <X className="w-3.5 h-3.5" />
            </button>
            <div className="absolute top-1 left-1 bg-state-success-bg text-state-success-fg text-[10px] font-semibold px-2 py-0.5 rounded-full">
              ✓ Cargada
            </div>
          </>
        ) : (
          <label className="flex flex-col items-center justify-center h-24 cursor-pointer bg-background/50">
            <ImagePlus className="w-6 h-6 text-muted-foreground mb-1" />
            <span className="text-xs text-muted-foreground">Seleccionar</span>
            <input type="file" accept="image/*" className="hidden" {...register} />
          </label>
        )}
      </div>
      <p className="text-xs text-center mt-1">
        <span className={hasFile ? "text-foreground font-medium" : "text-muted-foreground"}>
          {label}
        </span>
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </p>
      {error && <p className="text-red-500 text-xs mt-1 text-center">{error}</p>}
    </div>
  );
}

// ------------------------------------------------
// SUB-COMPONENTE: SECCIÓN DE REVISIÓN
// ------------------------------------------------

interface ReviewSectionProps {
  title:  string;
  items:  [string, string][];
  onEdit: () => void;
}

function ReviewSection({ title, items, onEdit }: ReviewSectionProps) {
  return (
    <div className="border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{title}</h3>
        <button
          type="button"
          onClick={onEdit}
          className="text-xs font-medium text-primary hover:text-primary-hover transition-colors"
        >
          Editar
        </button>
      </div>
      <div className="space-y-2">
        {items.map(([label, value]) => (
          <div key={label} className="flex justify-between text-sm gap-4">
            <span className="text-muted-foreground shrink-0">{label}</span>
            <span className="text-foreground font-medium text-right truncate">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}