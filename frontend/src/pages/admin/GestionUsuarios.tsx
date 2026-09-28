// src/pages/admin/GestionUsuarios.tsx

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import Layout from "../../components/Layout";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Alert";
import { Spinner } from "../../components/ui/Spinner";
import { Modal } from "../../components/ui/Modal";
import { EnlaceEnviadoModal } from "../../components/ui/EnlaceEnviadoModal";
import { catalogosService } from "../../services/catalogos.service";
import { estacionesService } from "../../services/estaciones.service";
import {
  usersService,
  type UserFuncionario,
  type TipoUsuario,
  type EstadoCuenta,
  type TipoDocumento,
  type CrearFuncionarioPayload,
  type EditarFuncionarioPayload,
} from "../../services/users.service";
import { formatFecha } from "../../utils/format";
import { ESTADOS_CUENTA } from "../../utils/constants";
import { EstadoCuentaBadge } from "../../components/ui/EstadoBadge";
import { useAuth } from "../../context/AuthContext";
import {
  Users, Plus, Search, RefreshCw,
  CheckCircle, UserCheck, UserX, KeyRound, AlertTriangle, Send,
} from "lucide-react";

// ------------------------------------------------
// CONSTANTES
// ------------------------------------------------

const TABS_ROL: { value: TipoUsuario | ""; label: string }[] = [
  { value: "",      label: "Todos" },
  { value: "ANH",   label: "ANH" },
  { value: "ESS",   label: "Estación" },
  { value: "ADMIN", label: "Administrador" },
];

// Coincide con PerfilFuncionario.TipoDocumento del backend.
const TIPOS_DOC: { value: TipoDocumento; label: string }[] = [
  { value: "CI",         label: "Cédula de Identidad" },
  { value: "PASAPORTE",  label: "Pasaporte" },
  { value: "EXTRANJERO", label: "Carnet de Extranjero" },
];

const rolColor: Record<string, string> = {
  ANH:   "bg-blue-100 text-blue-700",
  ESS:   "bg-purple-100 text-purple-700",
  ADMIN: "bg-slate-800 text-white",
};

const ALERT_TIMEOUT = 4000;

// ------------------------------------------------
// COMPONENTE PRINCIPAL
// ------------------------------------------------

export default function GestionUsuarios() {
  const { user: adminActual } = useAuth();

  const [usuarios, setUsuarios] = useState<UserFuncionario[]>([]);
  const [loading,  setLoading]  = useState(true);

  const [tipoUsuario,   setTipoUsuario]   = useState<TipoUsuario | "">("");
  const [estadoCuenta,  setEstadoCuenta]  = useState<EstadoCuenta | "">("");
  const [busquedaInput, setBusquedaInput] = useState("");
  const [busqueda,      setBusqueda]      = useState("");

  // Alerta global con auto-dismiss
  const [alerta, setAlertaMsg] = useState<{ type: "error" | "success"; message: string } | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flash = (type: "error" | "success", message: string) => {
    setAlertaMsg({ type, message });
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setAlertaMsg(null), ALERT_TIMEOUT);
  };

  // Modal crear/editar
  const [modalForm, setModalForm] = useState(false);
  const [editando,  setEditando]  = useState<UserFuncionario | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [errorForm, setErrorForm] = useState("");

  const [form, setForm] = useState({
    email: "", nombres: "", apellido_paterno: "", apellido_materno: "",
    tipo_usuario: "ANH" as "ANH" | "ESS" | "ADMIN",
    cargo: "", unidad_departamento: "", numero_funcionario: "",
    tipo_documento: "CI" as TipoDocumento, numero_documento: "", celular: "",
    departamento_id: 0, provincia_id: 0, municipio_id: 0,
    estacion_servicio_id: 0,
  });

  // Catálogo
  const [deptos,     setDeptos]     = useState<{ id: number; nombre: string }[]>([]);
  const [provs,      setProvs]      = useState<{ id: number; nombre: string }[]>([]);
  const [munis,      setMunis]      = useState<{ id: number; nombre: string }[]>([]);
  const [estaciones, setEstaciones] = useState<{ id: number; nombre: string }[]>([]);
  const [loadCatalogo, setLoadCatalogo] = useState(false);

  // Modal "enlace enviado" (al crear o al resetear). userId permite
  // reintentar desde el mismo modal si el email no salió.
  const [modalEnlace, setModalEnlace] = useState<{
    titulo:       string;
    email:        string;
    emailEnviado: boolean;
    tipo:         "activacion" | "recuperacion";
    userId:       number;
  } | null>(null);
  const [reenviandoModal, setReenviandoModal] = useState(false);

  // Reenvío de activación desde la fila
  const [reenviandoId, setReenviandoId] = useState<number | null>(null);

  // Cambio de estado
  const [cambiandoEstado, setCambiandoEstado] = useState<number | null>(null);

  // Reset de contraseña
  const [confirmarReset, setConfirmarReset] = useState<UserFuncionario | null>(null);
  const [reseteando,     setReseteando]     = useState(false);
  const [errorReset,     setErrorReset]     = useState("");

  useEffect(() => {
    catalogosService.getDepartamentos().then(setDeptos).catch(() => {});
  }, []);

  // ------------------------------------------------
  // CARGA DE USUARIOS
  // ------------------------------------------------

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const res = await usersService.listar();
      setUsuarios(res);
    } catch {
      flash("error", "Error al cargar los usuarios.");
      setUsuarios([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  // ------------------------------------------------
  // FILTRADO LOCAL (el backend no soporta paginación ni search aquí,
  // así que filtramos en el frontend sobre el array completo)
  // ------------------------------------------------

  const usuariosFiltrados = useMemo(() => {
    return usuarios.filter(u => {
      if (tipoUsuario  && u.tipo_usuario  !== tipoUsuario)  return false;
      if (estadoCuenta && u.estado_cuenta !== estadoCuenta) return false;
      if (!busqueda) return true;
      const q = busqueda.toLowerCase();
      return (
        u.nombre_completo.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        (u.perfil?.numero_documento ?? "").toLowerCase().includes(q) ||
        (u.perfil?.estacion_nombre ?? "").toLowerCase().includes(q)
      );
    });
  }, [usuarios, tipoUsuario, estadoCuenta, busqueda]);

  const onBuscar = (e: React.FormEvent) => {
    e.preventDefault();
    setBusqueda(busquedaInput);
  };

  // ------------------------------------------------
  // CASCADA GEOGRÁFICA (para ESS)
  // ------------------------------------------------

  const onDeptoChange = async (deptoId: number) => {
    setForm(f => ({ ...f, departamento_id: deptoId, provincia_id: 0, municipio_id: 0, estacion_servicio_id: 0 }));
    setProvs([]); setMunis([]); setEstaciones([]);
    if (!deptoId) return;
    setLoadCatalogo(true);
    try { setProvs(await catalogosService.getProvincias(deptoId)); }
    finally { setLoadCatalogo(false); }
  };

  const onProvChange = async (provId: number) => {
    setForm(f => ({ ...f, provincia_id: provId, municipio_id: 0, estacion_servicio_id: 0 }));
    setMunis([]); setEstaciones([]);
    if (!provId) return;
    setLoadCatalogo(true);
    try { setMunis(await catalogosService.getMunicipios(provId)); }
    finally { setLoadCatalogo(false); }
  };

  const onMuniChange = async (muniId: number) => {
    setForm(f => ({ ...f, municipio_id: muniId, estacion_servicio_id: 0 }));
    setEstaciones([]);
    if (!muniId) return;
    setLoadCatalogo(true);
    try {
      const data = await estacionesService.getAll({ municipio: String(muniId), estado: "ACTIVA" });
      setEstaciones(data.map(e => ({ id: e.id, nombre: e.nombre })));
    } finally { setLoadCatalogo(false); }
  };

  // ------------------------------------------------
  // ABRIR MODAL
  // ------------------------------------------------

  const abrirCrear = () => {
    setEditando(null);
    setErrorForm("");
    setForm({
      email: "", nombres: "", apellido_paterno: "", apellido_materno: "",
      tipo_usuario: "ANH", cargo: "", unidad_departamento: "", numero_funcionario: "",
      tipo_documento: "CI", numero_documento: "", celular: "",
      departamento_id: 0, provincia_id: 0, municipio_id: 0,
      estacion_servicio_id: 0,
    });
    setProvs([]); setMunis([]); setEstaciones([]);
    setModalForm(true);
  };

  const abrirEditar = (u: UserFuncionario) => {
    if (u.tipo_usuario === "CONSUMIDOR") return;

    setEditando(u);
    setErrorForm("");
    setForm({
      email: u.email, nombres: u.nombres,
      apellido_paterno: u.apellido_paterno, apellido_materno: u.apellido_materno ?? "",
      tipo_usuario: u.tipo_usuario as "ANH" | "ESS" | "ADMIN",
      cargo:               u.perfil?.cargo ?? "",
      unidad_departamento: u.perfil?.unidad_departamento ?? "",
      numero_funcionario:  u.perfil?.numero_funcionario ?? "",
      tipo_documento:      u.perfil?.tipo_documento ?? "CI",
      numero_documento:    u.perfil?.numero_documento ?? "",
      celular:             u.perfil?.celular ?? "",
      departamento_id: 0, provincia_id: 0, municipio_id: 0,
      estacion_servicio_id: u.perfil?.estacion_servicio_id ?? 0,
    });
    setProvs([]); setMunis([]); setEstaciones([]);
    setModalForm(true);
  };

  // ------------------------------------------------
  // GUARDAR
  // ------------------------------------------------

  const guardar = async () => {
    if (!form.email || !form.nombres || !form.apellido_paterno) {
      setErrorForm("Completa email, nombres y apellido paterno.");
      return;
    }

    // El backend crea un PerfilFuncionario para todo funcionario y
    // exige estos cuatro campos. Validarlos aquí evita un 400 tras
    // llenar el formulario entero.
    if (!editando && (
      !form.cargo.trim() ||
      !form.unidad_departamento.trim() ||
      !form.numero_funcionario.trim() ||
      !form.numero_documento.trim()
    )) {
      setErrorForm("Completa cargo, unidad, N° funcionario y N° documento.");
      return;
    }

    setGuardando(true); setErrorForm("");
    try {
      if (editando) {
        const payload: EditarFuncionarioPayload = {
          nombres:             form.nombres,
          apellido_paterno:    form.apellido_paterno,
          apellido_materno:    form.apellido_materno,
          cargo:               form.cargo,
          unidad_departamento: form.unidad_departamento,
          numero_funcionario:  form.numero_funcionario,
          tipo_documento:      form.tipo_documento,
          numero_documento:    form.numero_documento,
          celular:             form.celular,
        };
        // Solo se envía si se eligió una nueva: enviar 0 borraría la actual.
        if (form.tipo_usuario === "ESS" && form.estacion_servicio_id) {
          payload.estacion_servicio_id = form.estacion_servicio_id;
        }
        await usersService.actualizar(editando.id, payload);
        flash("success", "Usuario actualizado correctamente.");
        setModalForm(false);
      } else {
        const payload: CrearFuncionarioPayload = {
          email:               form.email,
          nombres:             form.nombres,
          apellido_paterno:    form.apellido_paterno,
          apellido_materno:    form.apellido_materno,
          tipo_usuario:        form.tipo_usuario,
          // Datos de perfil: obligatorios para los tres roles.
          cargo:               form.cargo,
          unidad_departamento: form.unidad_departamento,
          numero_funcionario:  form.numero_funcionario,
          tipo_documento:      form.tipo_documento,
          numero_documento:    form.numero_documento,
          celular:             form.celular,
        };
        // 0 significa "sin seleccionar": omitir el campo en vez de
        // mandar un pk inexistente (el backend lo rechazaría con 400).
        if (form.tipo_usuario === "ESS" && form.estacion_servicio_id) {
          payload.estacion_servicio = form.estacion_servicio_id;
        }

        const res = await usersService.crear(payload);
        setModalForm(false);
        setModalEnlace({
          titulo:       "Usuario creado",
          email:        res.email,
          emailEnviado: res.email_enviado,
          tipo:         "activacion",
          userId:       res.user_id,
        });
      }
      await cargar();
    } catch (err: unknown) {
      const e = err as { response?: { data?: unknown } };
      const d = e.response?.data;
      let msg = "Error al guardar el usuario.";
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
    } finally { setGuardando(false); }
  };

  // ------------------------------------------------
  // CAMBIAR ESTADO
  // ------------------------------------------------

  const cambiarEstado = async (u: UserFuncionario, nuevo: EstadoCuenta) => {
    setCambiandoEstado(u.id);
    try {
      await usersService.cambiarEstado(u.id, nuevo);
      flash("success", `Estado cambiado a ${ESTADOS_CUENTA[nuevo]?.label ?? nuevo}.`);
      await cargar();
    } catch {
      flash("error", "Error al cambiar el estado.");
    } finally { setCambiandoEstado(null); }
  };

  // ------------------------------------------------
  // RESETEAR CONTRASEÑA
  // ------------------------------------------------

  const resetearPassword = async () => {
    if (!confirmarReset) return;
    setReseteando(true);
    setErrorReset("");
    try {
      const res = await usersService.resetearPassword(confirmarReset.id);
      // No hace falta recargar el listado: el reset solo invalida la
      // contraseña y cierra sesiones, nada de eso se muestra en la tabla.
      setModalEnlace({
        titulo:       "Contraseña reseteada",
        email:        res.email,
        emailEnviado: res.email_enviado,
        tipo:         "recuperacion",
        userId:       confirmarReset.id,
      });
      setConfirmarReset(null);
    } catch (err: unknown) {
      const e = err as { response?: { data?: unknown } };
      const d = e.response?.data;
      let msg = "Error al resetear la contraseña.";
      if (typeof d === "string") {
        msg = d;
      } else if (d && typeof d === "object") {
        const detail = (d as Record<string, unknown>).detail;
        if (typeof detail === "string") msg = detail;
      }
      setErrorReset(msg);
    } finally {
      setReseteando(false);
    }
  };

  // ------------------------------------------------
  // REENVIAR ENLACE
  // ------------------------------------------------

  const reenviarActivacion = async (u: UserFuncionario) => {
    setReenviandoId(u.id);
    try {
      const res = await usersService.reenviarActivacion(u.id);
      if (res.email_enviado) {
        flash("success", `Se envió un nuevo enlace de activación a ${res.email}.`);
      } else {
        flash("error", "No se pudo enviar el email de activación. Intenta nuevamente.");
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      flash("error", e.response?.data?.detail ?? "Error al reenviar el enlace de activación.");
    } finally { setReenviandoId(null); }
  };

  // Reintento desde el modal cuando el email del alta o del reset no salió.
  // En el reset se repite el reset (genera un link nuevo e invalida el anterior).
  const reintentarEnvio = async () => {
    if (!modalEnlace) return;
    setReenviandoModal(true);
    try {
      const res = modalEnlace.tipo === "activacion"
        ? await usersService.reenviarActivacion(modalEnlace.userId)
        : await usersService.resetearPassword(modalEnlace.userId);
      setModalEnlace({ ...modalEnlace, emailEnviado: res.email_enviado });
    } catch {
      setModalEnlace({ ...modalEnlace, emailEnviado: false });
    } finally { setReenviandoModal(false); }
  };

  const inputCls = "w-full px-4 py-2.5 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none";

  return (
    <Layout>
      <div className="space-y-5">

        {/* TÍTULO */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-navbar rounded-xl flex items-center justify-center">
              <Users className="w-5 h-5 text-navbar-foreground" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">Gestión de Usuarios</h1>
              <p className="text-muted-foreground text-sm">{usuarios.length} usuarios registrados</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="primary" icon={<Plus className="w-4 h-4" />} onClick={abrirCrear}>
              Nuevo usuario
            </Button>
            <Button variant="outline" icon={<RefreshCw className="w-4 h-4" />} onClick={cargar}>
              <span className="sr-only">Actualizar</span>
            </Button>
          </div>
        </div>

        {alerta && <Alert type={alerta.type} message={alerta.message} />}

        <Card>

          {/* TABS DE ROL */}
          <div className="flex items-center border-b border-border overflow-x-auto">
            {TABS_ROL.map(tab => (
              <button key={tab.value} onClick={() => setTipoUsuario(tab.value)}
                className={`px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                  tipoUsuario === tab.value ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
                }`}>
                {tab.label}
              </button>
            ))}
          </div>

          {/* BÚSQUEDA + FILTRO ESTADO */}
          <div className="px-4 pt-4 pb-2 flex gap-2 flex-wrap">
            <form onSubmit={onBuscar} className="flex-1 flex gap-2 min-w-0">
              <div className="relative flex-1 min-w-0">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input value={busquedaInput} onChange={e => setBusquedaInput(e.target.value)}
                  placeholder={`Buscar${tipoUsuario ? ` en ${TABS_ROL.find(t => t.value === tipoUsuario)?.label}` : " por nombre, email o CI"}...`}
                  className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-border text-sm bg-input focus:border-primary focus:ring-2 focus:ring-primary/20 focus:bg-card outline-none" />
              </div>
              <Button variant="primary" size="md" type="submit">Buscar</Button>
              {busqueda && (
                <Button variant="outline" size="md" type="button" onClick={() => { setBusquedaInput(""); setBusqueda(""); }}>
                  Limpiar
                </Button>
              )}
            </form>
            <select value={estadoCuenta} onChange={e => setEstadoCuenta(e.target.value as EstadoCuenta | "")}
              className="px-3 py-2.5 rounded-xl border border-border text-sm bg-input outline-none focus:border-primary focus:ring-2 focus:ring-primary/20">
              <option value="">Todos los estados</option>
              {Object.entries(ESTADOS_CUENTA).map(([value, { label }]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          {/* TABLA */}
          {loading ? (
            <div className="flex items-center justify-center py-16"><Spinner size="lg" /></div>
          ) : usuariosFiltrados.length === 0 ? (
            <div className="text-center py-16 px-4">
              <Users className="w-12 h-12 text-border mx-auto mb-3" />
              <p className="text-foreground font-medium mb-1">Sin usuarios</p>
              <p className="text-muted-foreground text-sm">
                {busqueda ? `No se encontraron usuarios para "${busqueda}".` : "No hay usuarios con este filtro."}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Usuario</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Rol</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Estado</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wide">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {usuariosFiltrados.map(u => {
                    const subtexto = [
                      u.email,
                      u.tipo_usuario === "ESS" && u.perfil?.estacion_nombre
                        ? `Estación: ${u.perfil.estacion_nombre}`
                        : null,
                      u.perfil?.cargo || null,
                      `Registro: ${formatFecha(u.date_joined)}`,
                    ].filter(Boolean).join(" · ");

                    return (
                      <tr key={u.id} className="hover:bg-background transition-colors">
                        <td className="px-4 py-3">
                          <p className="text-sm font-medium text-foreground">{u.nombre_completo}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">{subtexto}</p>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${rolColor[u.tipo_usuario] ?? "bg-background text-muted-foreground"}`}>
                              {u.tipo_usuario}
                            </span>
                            {u.tipo_usuario === "ESS" && !u.perfil?.estacion_nombre && (
                              <span className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full bg-state-warning-bg text-state-warning-fg">
                                <AlertTriangle className="w-3 h-3" />
                                Sin estación
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <EstadoCuentaBadge estado={u.estado_cuenta} />
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1 justify-end flex-wrap">
                            {u.tipo_usuario !== "CONSUMIDOR" && (
                              <Button variant="ghost" size="sm" onClick={() => abrirEditar(u)}>Editar</Button>
                            )}
                            {/* Una cuenta PENDIENTE solo se activa con el link:
                                ni activar/suspender a mano ni resetear (el backend
                                rechaza el cambio de estado con 400). */}
                            {u.estado_cuenta === "PENDIENTE" ? (
                              <Button variant="ghost" size="sm" icon={<Send className="w-3.5 h-3.5" />}
                                loading={reenviandoId === u.id} onClick={() => reenviarActivacion(u)}>
                                Reenviar enlace
                              </Button>
                            ) : u.estado_cuenta === "ACTIVO" ? (
                              <Button variant="ghost" size="sm" icon={<UserX className="w-3.5 h-3.5" />}
                                loading={cambiandoEstado === u.id} onClick={() => cambiarEstado(u, "SUSPENDIDO")}>
                                <span className="sr-only">Suspender</span>
                              </Button>
                            ) : (
                              <Button variant="ghost" size="sm" icon={<UserCheck className="w-3.5 h-3.5" />}
                                loading={cambiandoEstado === u.id} onClick={() => cambiarEstado(u, "ACTIVO")}>
                                <span className="sr-only">Activar</span>
                              </Button>
                            )}
                            {u.tipo_usuario !== "CONSUMIDOR" && u.id !== adminActual?.id && u.estado_cuenta !== "PENDIENTE" && (
                              <Button variant="ghost" size="sm" icon={<KeyRound className="w-3.5 h-3.5" />}
                                onClick={() => { setErrorReset(""); setConfirmarReset(u); }}>
                                <span className="sr-only">Resetear contraseña</span>
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* MODAL CREAR / EDITAR */}
      <Modal open={modalForm} onClose={() => setModalForm(false)}
        title={editando ? "Editar usuario" : "Nuevo usuario"} size="lg">
        <div className="space-y-4">
          {errorForm && <Alert type="error" message={errorForm} />}

          {!editando && (
            <Alert type="info" message="El usuario recibirá un enlace por email para crear su contraseña y activar la cuenta." />
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Email *</label>
              <input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value.toLowerCase() }))}
                disabled={!!editando} className={inputCls + (editando ? " opacity-60" : "")} />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Tipo de usuario *</label>
              <select value={form.tipo_usuario} onChange={e => setForm(f => ({ ...f, tipo_usuario: e.target.value as "ANH" | "ESS" | "ADMIN" }))}
                disabled={!!editando} className={inputCls + (editando ? " opacity-60" : "")}>
                <option value="ANH">ANH</option>
                <option value="ESS">Estación de Servicio (ESS)</option>
                <option value="ADMIN">Administrador</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Nombres *</label>
              <input value={form.nombres} onChange={e => setForm(f => ({ ...f, nombres: e.target.value }))} className={inputCls} />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Apellido paterno *</label>
              <input value={form.apellido_paterno} onChange={e => setForm(f => ({ ...f, apellido_paterno: e.target.value }))} className={inputCls} />
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-muted-foreground mb-1">Apellido materno</label>
              <input value={form.apellido_materno} onChange={e => setForm(f => ({ ...f, apellido_materno: e.target.value }))} className={inputCls} />
            </div>
          </div>

          {/* Datos del funcionario — el backend los exige para los tres roles */}
          <div className="border border-border rounded-xl p-4 bg-background/50 space-y-3">
            <p className="text-xs font-medium text-foreground">Datos del funcionario</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Cargo *</label>
                <input value={form.cargo} onChange={e => setForm(f => ({ ...f, cargo: e.target.value }))} className={inputCls} placeholder="Ej: Analista" />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Unidad / Departamento *</label>
                <input value={form.unidad_departamento} onChange={e => setForm(f => ({ ...f, unidad_departamento: e.target.value }))} className={inputCls} />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">N° funcionario *</label>
                <input value={form.numero_funcionario} onChange={e => setForm(f => ({ ...f, numero_funcionario: e.target.value }))} className={inputCls} placeholder="Ej: ANH-001" />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Celular</label>
                <input
                  value={form.celular}
                  onChange={e => setForm(f => ({ ...f, celular: e.target.value }))}
                  className={inputCls}
                  inputMode="numeric"
                  placeholder="Ej: 78123456"
                  onInput={e => {
                    const el = e.target as HTMLInputElement;
                    el.value = el.value.replace(/\D/g, "");
                  }}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Tipo documento *</label>
                <select value={form.tipo_documento} onChange={e => setForm(f => ({ ...f, tipo_documento: e.target.value as TipoDocumento }))} className={inputCls}>
                  {TIPOS_DOC.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">N° documento *</label>
                <input value={form.numero_documento} onChange={e => setForm(f => ({ ...f, numero_documento: e.target.value }))} className={inputCls} />
              </div>
            </div>
          </div>

          {/* Cascada geográfica solo para ESS */}
          {form.tipo_usuario === "ESS" && (
            <div className="border border-border rounded-xl p-4 bg-background/50 space-y-3">
              <p className="text-xs font-medium text-foreground">
                Estación asignada (opcional)
              </p>
              <p className="text-xs text-muted-foreground">
                Selecciona el departamento, provincia y municipio para filtrar estaciones activas.
                Un ESS puede quedar sin estación hasta que se le asigne una.
              </p>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Departamento</label>
                  <select value={form.departamento_id} onChange={e => onDeptoChange(Number(e.target.value))} className={inputCls}>
                    <option value={0}>Seleccionar...</option>
                    {deptos.map(d => <option key={d.id} value={d.id}>{d.nombre}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Provincia</label>
                  <select value={form.provincia_id} onChange={e => onProvChange(Number(e.target.value))}
                    disabled={!form.departamento_id || loadCatalogo} className={inputCls + " disabled:opacity-50"}>
                    <option value={0}>{loadCatalogo ? "Cargando..." : "Seleccionar..."}</option>
                    {provs.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Municipio</label>
                  <select value={form.municipio_id} onChange={e => onMuniChange(Number(e.target.value))}
                    disabled={!form.provincia_id || loadCatalogo} className={inputCls + " disabled:opacity-50"}>
                    <option value={0}>{loadCatalogo ? "Cargando..." : "Seleccionar..."}</option>
                    {munis.map(m => <option key={m.id} value={m.id}>{m.nombre}</option>)}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Estación</label>
                <select value={form.estacion_servicio_id} onChange={e => setForm(f => ({ ...f, estacion_servicio_id: Number(e.target.value) }))}
                  disabled={!form.municipio_id || loadCatalogo} className={inputCls + " disabled:opacity-50"}>
                  <option value={0}>
                    {!form.municipio_id ? "Sin asignar"
                      : loadCatalogo ? "Cargando..."
                      : estaciones.length === 0 ? "Sin estaciones activas en este municipio"
                      : "Sin asignar"}
                  </option>
                  {estaciones.map(e => <option key={e.id} value={e.id}>{e.nombre}</option>)}
                </select>
                {editando && editando.perfil?.estacion_nombre && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Estación actual: <strong>{editando.perfil.estacion_nombre}</strong>. Si no seleccionas una nueva, se mantiene.
                  </p>
                )}
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <Button variant="outline" onClick={() => setModalForm(false)}>Cancelar</Button>
            <Button variant="primary" icon={<CheckCircle className="w-4 h-4" />} loading={guardando} onClick={guardar}>
              {editando ? "Actualizar" : "Crear usuario"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* MODAL ENLACE ENVIADO (al crear o al resetear) */}
      <EnlaceEnviadoModal
        open={!!modalEnlace}
        onClose={() => setModalEnlace(null)}
        titulo={modalEnlace?.titulo ?? ""}
        email={modalEnlace?.email ?? ""}
        emailEnviado={modalEnlace?.emailEnviado ?? true}
        tipo={modalEnlace?.tipo ?? "activacion"}
        onReenviar={reintentarEnvio}
        reenviando={reenviandoModal}
      />

      {/* MODAL CONFIRMACIÓN — RESETEAR CONTRASEÑA */}
      <Modal open={!!confirmarReset} onClose={() => { if (!reseteando) setConfirmarReset(null); }}
        title="Resetear contraseña" size="sm">
        {confirmarReset && (
          <div className="space-y-4">
            {errorReset && <Alert type="error" message={errorReset} />}

            <p className="text-sm text-foreground">
              ¿Resetear la contraseña de <strong>{confirmarReset.nombre_completo}</strong> ({confirmarReset.email})?
            </p>

            <div className="flex items-start gap-2 text-xs text-muted-foreground bg-background rounded-xl p-3 border border-border">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-state-warning-fg" />
              <span>
                La contraseña actual dejará de funcionar y el usuario recibirá un
                enlace por email para crear una nueva.
                <br /><br />
                Se cerrarán las sesiones del usuario. Una sesión ya abierta puede
                seguir activa hasta 30 minutos. Si necesitas cortar el acceso de
                inmediato, suspende la cuenta.
              </span>
            </div>

            <div className="flex justify-end gap-3 pt-1">
              <Button variant="outline" disabled={reseteando} onClick={() => setConfirmarReset(null)}>
                Cancelar
              </Button>
              <Button variant="danger" icon={<KeyRound className="w-4 h-4" />}
                loading={reseteando} onClick={resetearPassword}>
                Resetear contraseña
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </Layout>
  );
}