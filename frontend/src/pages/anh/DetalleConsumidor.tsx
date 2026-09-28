// src/pages/anh/DetalleConsumidor.tsx

import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Layout from "../../components/Layout";
import { Card, CardHeader, CardBody } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { Spinner } from "../../components/ui/Spinner";
import { EstadoIdentidadBadge, AlertaBadge } from "../../components/ui/EstadoBadge";
import { EnlaceEnviadoModal } from "../../components/ui/EnlaceEnviadoModal";
import { Modal } from "../../components/ui/Modal";
import { consumidoresService } from "../../services/consumidores.service";
import { usersService } from "../../services/users.service";
import type { ConsumidorPerfil } from "../../types/consumidor.types";
import { ACTIVIDADES } from "../../utils/constants";
import { formatFecha } from "../../utils/format";
import {
  ArrowLeft, User, MapPin, Shield,
  FileImage, AlertCircle, CheckCircle, ShieldAlert, ShieldOff, KeyRound, Send,
} from "lucide-react";

const ALERT_TIMEOUT = 4000;

function Dato({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground mb-0.5">{label}</p>
      <p className="text-sm font-medium text-foreground">{value ?? "—"}</p>
    </div>
  );
}

export default function DetalleConsumidor() {
  const { id }   = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [perfil,     setPerfil]     = useState<ConsumidorPerfil | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState("");
  const [procesando, setProcesando] = useState(false);

  // Alertas con auto-dismiss
  const [alerta, setAlertaMsg] = useState<{ type: "error" | "success"; message: string } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flash = (type: "error" | "success", message: string) => {
    setAlertaMsg({ type, message });
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setAlertaMsg(null), ALERT_TIMEOUT);
  };

  // Motivos separados para identidad y alerta (antes compartían
  // el mismo estado, lo cual era un bug si ambos estaban abiertos).
  const [accionIdentidad, setAccionIdentidad] = useState<string | null>(null);
  const [motivoIdentidad, setMotivoIdentidad] = useState("");

  const [accionAlerta, setAccionAlerta] = useState<string | null>(null);
  const [motivoAlerta, setMotivoAlerta] = useState("");

  // Reset de contraseña
  const [confirmarReset, setConfirmarReset] = useState(false);
  const [reseteando,     setReseteando]     = useState(false);
  const [errorReset,     setErrorReset]     = useState("");
  const [modalEnlace,    setModalEnlace]    = useState<{ email: string; emailEnviado: boolean } | null>(null);
  const [reintentando,   setReintentando]   = useState(false);

  // Reenvío de activación (cuenta PENDIENTE)
  const [reenviando, setReenviando] = useState(false);

  useEffect(() => {
    if (!id) return;
    consumidoresService.getById(Number(id))
      .then(setPerfil)
      .catch(() => setError("Error al cargar el consumidor."))
      .finally(() => setLoading(false));
  }, [id]);

  const cambiarIdentidad = async (estado: string) => {
    if (!perfil) return;
    setProcesando(true);
    try {
      const p = await consumidoresService.verificarIdentidad(perfil.id, {
        estado_identidad: estado,
        observacion: motivoIdentidad,
      });
      setPerfil(p);
      setAccionIdentidad(null);
      setMotivoIdentidad("");
      flash("success", `Estado de identidad actualizado a: ${estado}`);
    } catch {
      flash("error", "Error al cambiar el estado de identidad.");
    } finally { setProcesando(false); }
  };

  const cambiarAlerta = async (alertaVal: string) => {
    if (!perfil) return;
    setProcesando(true);
    try {
      const p = await consumidoresService.cambiarAlerta(perfil.id, {
        alerta_repetitividad: alertaVal,
        motivo: motivoAlerta,
      });
      setPerfil(p);
      setAccionAlerta(null);
      setMotivoAlerta("");
      flash("success", `Alerta actualizada a: ${alertaVal}`);
    } catch {
      flash("error", "Error al cambiar la alerta.");
    } finally { setProcesando(false); }
  };

  const resetearPassword = async () => {
    if (!perfil) return;
    setReseteando(true);
    setErrorReset("");
    try {
      const res = await consumidoresService.resetearPassword(perfil.id);
      setConfirmarReset(false);
      // No hace falta recargar el perfil: el reset no toca ningún
      // campo que se muestre en esta pantalla.
      setModalEnlace({ email: res.email, emailEnviado: res.email_enviado });
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setErrorReset(e.response?.data?.detail ?? "Error al resetear la contraseña.");
    } finally {
      setReseteando(false);
    }
  };

  // Reintento desde el modal si el email del reset no salió: repite el
  // reset (link nuevo, el anterior queda invalidado).
  const reintentarReset = async () => {
    if (!perfil || !modalEnlace) return;
    setReintentando(true);
    try {
      const res = await consumidoresService.resetearPassword(perfil.id);
      setModalEnlace({ email: res.email, emailEnviado: res.email_enviado });
    } catch {
      setModalEnlace({ ...modalEnlace, emailEnviado: false });
    } finally { setReintentando(false); }
  };

  const reenviarActivacion = async () => {
    if (!perfil) return;
    setReenviando(true);
    try {
      const res = await usersService.reenviarActivacion(perfil.user.id);
      if (res.email_enviado) {
        flash("success", `Se envió un nuevo enlace de activación a ${res.email}.`);
      } else {
        flash("error", "No se pudo enviar el email de activación. Intenta nuevamente.");
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      flash("error", e.response?.data?.detail ?? "Error al reenviar el enlace de activación.");
    } finally { setReenviando(false); }
  };

  const textareaCls = "w-full px-4 py-2.5 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none resize-none";

  if (loading) return (
    <Layout>
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    </Layout>
  );

  if (!perfil) return (
    <Layout>
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 max-w-md mx-auto text-center">
        <Alert type="error" message={error || "Consumidor no encontrado."} />
        <Button variant="outline" onClick={() => navigate(-1)}>Volver</Button>
      </div>
    </Layout>
  );

  return (
    <Layout>
      <div className="max-w-3xl mx-auto space-y-5">

        {/* HEADER */}
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <div className="flex-1">
            <h1 className="text-xl font-bold text-foreground">
              {perfil.user.nombres} {perfil.user.apellido_paterno} {perfil.user.apellido_materno}
            </h1>
            <p className="text-muted-foreground text-sm">{perfil.user.email}</p>
          </div>
          <div className="flex gap-2">
            <EstadoIdentidadBadge estado={perfil.estado_identidad} />
            {perfil.alerta_repetitividad && perfil.alerta_repetitividad !== "NORMAL" && (
              <AlertaBadge alerta={perfil.alerta_repetitividad} />
            )}
          </div>
        </div>

        {alerta && <Alert type={alerta.type} message={alerta.message} />}

        {/* DATOS PERSONALES + ACTIVIDAD (fusionados) */}
        <Card>
          <CardHeader>
            <h2 className="font-semibold text-foreground flex items-center gap-2">
              <User className="w-4 h-4 text-primary" />
              Datos personales
            </h2>
          </CardHeader>
          <CardBody>
            <div className="grid grid-cols-2 gap-4">
              <Dato label="Nombres"          value={perfil.user.nombres} />
              <Dato label="Primer apellido"  value={perfil.user.apellido_paterno} />
              <Dato label="Segundo apellido" value={perfil.user.apellido_materno} />
              <Dato label="Email"            value={perfil.user.email} />
              <Dato label="Celular"          value={perfil.celular || "—"} />
              <Dato label="Fecha nacimiento" value={formatFecha(perfil.fecha_nacimiento)} />
              <Dato label="Actividad económica" value={ACTIVIDADES[perfil.actividad] ?? perfil.actividad} />
              <Dato label="Registro"         value={formatFecha(perfil.fecha_creacion, true)} />
            </div>
          </CardBody>
        </Card>

        {/* UBICACIÓN */}
        <Card>
          <CardHeader>
            <h2 className="font-semibold text-foreground flex items-center gap-2">
              <MapPin className="w-4 h-4 text-primary" />
              Ubicación
            </h2>
          </CardHeader>
          <CardBody>
            <div className="grid grid-cols-2 gap-4">
              <Dato label="Departamento" value={perfil.departamento_nombre} />
              <Dato label="Provincia"    value={perfil.provincia_nombre} />
              <Dato label="Municipio"    value={perfil.municipio_nombre} />
              <Dato label="Dirección"    value={perfil.direccion} />
            </div>
          </CardBody>
        </Card>

        {/* VERIFICACIÓN DE IDENTIDAD */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <h2 className="font-semibold text-foreground flex items-center gap-2">
              <Shield className="w-4 h-4 text-primary" />
              Verificación de identidad
            </h2>
            <EstadoIdentidadBadge estado={perfil.estado_identidad} />
          </CardHeader>
          <CardBody>
            {!accionIdentidad ? (
              <div className="flex gap-2 flex-wrap">
                {perfil.estado_identidad !== "VERIFICADO" && (
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<CheckCircle className="w-3.5 h-3.5" />}
                    onClick={() => { setAccionIdentidad("VERIFICADO"); setMotivoIdentidad(""); }}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    Verificar
                  </Button>
                )}
                {perfil.estado_identidad !== "EN_REVISION" && (
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<ShieldAlert className="w-3.5 h-3.5" />}
                    onClick={() => { setAccionIdentidad("EN_REVISION"); setMotivoIdentidad(""); }}
                    className="bg-amber-500 hover:bg-amber-600"
                  >
                    En revisión
                  </Button>
                )}
                {perfil.estado_identidad !== "RECHAZADO" && (
                  <Button
                    variant="danger"
                    size="sm"
                    icon={<ShieldOff className="w-3.5 h-3.5" />}
                    onClick={() => { setAccionIdentidad("RECHAZADO"); setMotivoIdentidad(""); }}
                  >
                    Rechazar
                  </Button>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm font-medium text-foreground">
                  Cambiar a: <span className="text-primary">{accionIdentidad}</span>
                </p>
                <textarea
                  value={motivoIdentidad}
                  onChange={e => setMotivoIdentidad(e.target.value)}
                  rows={2}
                  placeholder={accionIdentidad === "RECHAZADO" ? "Motivo del rechazo (obligatorio)..." : "Observación (opcional)..."}
                  className={textareaCls}
                />
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setAccionIdentidad(null)}>
                    Cancelar
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<CheckCircle className="w-3.5 h-3.5" />}
                    loading={procesando}
                    onClick={() => cambiarIdentidad(accionIdentidad)}
                  >
                    Confirmar
                  </Button>
                </div>
              </div>
            )}
          </CardBody>
        </Card>

        {/* ALERTA DE REPETITIVIDAD */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <h2 className="font-semibold text-foreground flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-primary" />
              Alerta de repetitividad
            </h2>
            <AlertaBadge alerta={perfil.alerta_repetitividad} />
          </CardHeader>
          <CardBody>
            {perfil.motivo_bloqueo && (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-4 py-2 mb-3">
                {perfil.motivo_bloqueo}
              </p>
            )}
            {perfil.fecha_alerta && (
              <p className="text-xs text-muted-foreground mb-3">
                Alerta desde: {formatFecha(perfil.fecha_alerta, true)}
              </p>
            )}

            {!accionAlerta ? (
              <div className="flex gap-2 flex-wrap">
                {perfil.alerta_repetitividad !== "NORMAL" && (
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<CheckCircle className="w-3.5 h-3.5" />}
                    onClick={() => { setAccionAlerta("NORMAL"); setMotivoAlerta(""); }}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    Resolver alerta
                  </Button>
                )}
                {perfil.alerta_repetitividad !== "EN_REVISION" && (
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<ShieldAlert className="w-3.5 h-3.5" />}
                    onClick={() => { setAccionAlerta("EN_REVISION"); setMotivoAlerta(""); }}
                    className="bg-amber-500 hover:bg-amber-600"
                  >
                    Poner en revisión
                  </Button>
                )}
                {perfil.alerta_repetitividad !== "BLOQUEADO" && (
                  <Button
                    variant="danger"
                    size="sm"
                    icon={<ShieldOff className="w-3.5 h-3.5" />}
                    onClick={() => { setAccionAlerta("BLOQUEADO"); setMotivoAlerta(""); }}
                  >
                    Bloquear
                  </Button>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm font-medium text-foreground">
                  Cambiar alerta a: <span className="text-primary">{accionAlerta}</span>
                </p>
                <textarea
                  value={motivoAlerta}
                  onChange={e => setMotivoAlerta(e.target.value)}
                  rows={2}
                  placeholder={accionAlerta === "BLOQUEADO" ? "Motivo del bloqueo (obligatorio)..." : "Observación (opcional)..."}
                  className={textareaCls}
                />
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setAccionAlerta(null)}>
                    Cancelar
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<CheckCircle className="w-3.5 h-3.5" />}
                    loading={procesando}
                    onClick={() => cambiarAlerta(accionAlerta)}
                  >
                    Confirmar
                  </Button>
                </div>
              </div>
            )}
          </CardBody>
        </Card>

        {/* ACCIONES DE CUENTA */}
        <Card>
          <CardHeader>
            <h2 className="font-semibold text-foreground flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-primary" />
              Acciones de cuenta
            </h2>
          </CardHeader>
          <CardBody>
            {/* Cuenta PENDIENTE: todavía no creó su contraseña, así que
                la acción que corresponde es reenviar el link, no resetear. */}
            {perfil.user.estado_cuenta === "PENDIENTE" ? (
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                  <p className="text-sm font-medium text-foreground">Activación pendiente</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    El consumidor todavía no activó su cuenta con el enlace que recibió por email.
                  </p>
                </div>
                <Button
                  variant="outline"
                  icon={<Send className="w-4 h-4" />}
                  loading={reenviando}
                  onClick={reenviarActivacion}
                >
                  Reenviar enlace de activación
                </Button>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                  <p className="text-sm font-medium text-foreground">Contraseña</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Resetea la contraseña si el consumidor no puede ingresar y olvidó su clave.
                  </p>
                </div>
                <Button
                  variant="outline"
                  icon={<KeyRound className="w-4 h-4" />}
                  onClick={() => { setErrorReset(""); setConfirmarReset(true); }}
                >
                  Resetear contraseña
                </Button>
              </div>
            )}
          </CardBody>
        </Card>

        {/* DOCUMENTOS */}
        {perfil.documentos.length > 0 && (
          <Card>
            <CardHeader>
              <h2 className="font-semibold text-foreground flex items-center gap-2">
                <FileImage className="w-4 h-4 text-primary" />
                Documentos de identidad
              </h2>
            </CardHeader>
            {perfil.documentos.map(doc => (
              <CardBody key={doc.id} className="border-b border-border last:border-0">
                <p className="text-sm font-semibold text-foreground mb-1">{doc.tipo_documento_display}</p>
                <p className="text-xs text-muted-foreground mb-3">
                  N°: {doc.numero_documento} {doc.complemento_documento}
                </p>
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: "Anverso", url: doc.anverso },
                    { label: "Reverso", url: doc.reverso },
                    { label: "Sosteniendo", url: doc.foto_sosteniendo },
                  ].map(({ label, url }) => url ? (
                    <a key={label} href={url} target="_blank" rel="noreferrer"
                      className="block rounded-xl overflow-hidden border border-border hover:border-primary transition-colors">
                      <img src={url} alt={label} className="w-full h-24 object-cover" />
                      <p className="text-xs text-center text-muted-foreground py-1">{label}</p>
                    </a>
                  ) : null)}
                </div>
              </CardBody>
            ))}
          </Card>
        )}
      </div>

      {/* MODAL CONFIRMACIÓN — RESETEAR CONTRASEÑA */}
      <Modal open={confirmarReset} onClose={() => { if (!reseteando) setConfirmarReset(false); }}
        title="Resetear contraseña" size="sm">
        <div className="space-y-4">
          {errorReset && <Alert type="error" message={errorReset} />}

          <p className="text-sm text-foreground">
            ¿Resetear la contraseña de{" "}
            <strong>{perfil.user.nombres} {perfil.user.apellido_paterno}</strong> ({perfil.user.email})?
          </p>

          <div className="flex items-start gap-2 text-xs text-muted-foreground bg-background rounded-xl p-3 border border-border">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-state-warning-fg" />
            <span>
              La contraseña actual dejará de funcionar y el consumidor recibirá un
              enlace por email para crear una nueva.
              <br /><br />
              Se cerrarán las sesiones del usuario. Una sesión ya abierta puede
              seguir activa hasta 30 minutos.
            </span>
          </div>

          {perfil.alerta_repetitividad === "BLOQUEADO" && (
            <div className="flex items-start gap-2 text-xs text-state-warning-fg bg-state-warning-bg rounded-xl p-3">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                Este consumidor está bloqueado por repetitividad. Resetear la
                contraseña no levanta ese bloqueo — sus solicitudes seguirán
                rechazándose hasta que se resuelva la alerta. Solo le permite
                volver a iniciar sesión.
              </span>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-1">
            <Button variant="outline" disabled={reseteando} onClick={() => setConfirmarReset(false)}>
              Cancelar
            </Button>
            <Button variant="danger" icon={<KeyRound className="w-4 h-4" />}
              loading={reseteando} onClick={resetearPassword}>
              Resetear contraseña
            </Button>
          </div>
        </div>
      </Modal>

      {/* MODAL ENLACE ENVIADO (reset) */}
      <EnlaceEnviadoModal
        open={!!modalEnlace}
        onClose={() => setModalEnlace(null)}
        titulo="Contraseña reseteada"
        email={modalEnlace?.email ?? ""}
        emailEnviado={modalEnlace?.emailEnviado ?? true}
        tipo="recuperacion"
        onReenviar={reintentarReset}
        reenviando={reintentando}
      />
    </Layout>
  );
}