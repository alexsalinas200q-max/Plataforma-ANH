// src/App.tsx

import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";

// Páginas públicas
import Login       from "./pages/Login";
import Unauthorized from "./pages/Unauthorized";

// Páginas consumidor (lazy)
import { lazy, Suspense } from "react";

const RegistroConsumidor  = lazy(() => import("./pages/consumidor/Registro"));
const VerificarPin        = lazy(() => import("./pages/consumidor/VerificarPin"));
const MiSolicitud         = lazy(() => import("./pages/consumidor/MiSolicitud"));
const MiPerfil            = lazy(() => import("./pages/consumidor/MiPerfil"));
const RecuperarPassword   = lazy(() => import("./pages/RecuperarPassword"));
const ConfirmarRecuperacion = lazy(() => import("./pages/ConfirmarRecuperacion"));
const CambiarPasswordObligatorio = lazy(() => import("./pages/CambiarPasswordObligatorio"));

// Perfil compartido por ANH, ADMIN y ESS (ver el propio archivo
// para el porqué de un solo componente en vez de uno por rol).
const MiPerfilFuncionario = lazy(() => import("./pages/MiPerfilFuncionario"));

// Páginas ANH/ADMIN
const DashboardANH        = lazy(() => import("./pages/anh/Dashboard"));
const SolicitudesANH      = lazy(() => import("./pages/anh/Solicitudes"));
const DetalleSolicitudANH = lazy(() => import("./pages/anh/DetalleSolicitud"));
const ConsumidoresANH     = lazy(() => import("./pages/anh/Consumidores"));
const DetalleConsumidor   = lazy(() => import("./pages/anh/DetalleConsumidor"));
const EstacionesANH       = lazy(() => import("./pages/anh/Estaciones"));
const ReportesANH         = lazy(() => import("./pages/anh/Reportes"));
const GestionUsuarios = lazy(() => import("./pages/admin/GestionUsuarios"));
const RegistrarConsumidor = lazy(() => import("./pages/admin/RegistrarConsumidor"));
const EstacionesDepartamento = lazy(() => import("./pages/anh/EstacionesDepartamento"));
const EstacionesProvincia    = lazy(() => import("./pages/anh/EstacionesProvincia"));
// Páginas ESS
const SolicitudesESS      = lazy(() => import("./pages/estacion/Solicitudes"));
const HistorialESS        = lazy(() => import("./pages/estacion/Historial"));

// Loading fallback
const PageLoader = () => (
  <div className="min-h-[60vh] flex items-center justify-center">
    <div className="flex flex-col items-center gap-3">
      <div className="w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full animate-spin" />
      <p className="text-slate-500 text-sm">Cargando...</p>
    </div>
  </div>
);

// ------------------------------------------------
// REDIRECCIÓN POR ROL
// ------------------------------------------------

function RoleRedirect() {
  const { user, loading, isAuthenticated } = useAuth();

  if (loading) return <PageLoader />;
  if (!isAuthenticated || !user) return <Navigate to="/login" replace />;

  switch (user.tipo_usuario) {
    case "CONS":  return <Navigate to="/consumidor/solicitud"  replace />;
    case "ESS":   return <Navigate to="/estacion/solicitudes"  replace />;
    case "ANH":
    case "ADMIN": return <Navigate to="/anh/dashboard"         replace />;
    default:      return <Navigate to="/login"                 replace />;
  }
}

// ------------------------------------------------
// RUTAS
// ------------------------------------------------

function AppRoutes() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>

        {/* ---- PÚBLICAS ---- */}
        <Route path="/login"    element={<Login />} />
        <Route path="/registro" element={<RegistroConsumidor />} />
        <Route path="/verificar-email" element={<VerificarPin />} />
        <Route path="/recuperar-password" element={<RecuperarPassword />} />
        <Route path="/recuperar-password/confirmar" element={<ConfirmarRecuperacion />} />
        <Route path="/activar-cuenta" element={<ConfirmarRecuperacion modo="activacion" />} />
        <Route path="/reenviar-activacion" element={<RecuperarPassword modo="activacion" />} />
        <Route path="/unauthorized"    element={<Unauthorized />} />

        {/* ---- REDIRECCIÓN POR ROL ---- */}
        <Route path="/" element={<RoleRedirect />} />

        {/* ---- CAMBIO DE CONTRASEÑA OBLIGATORIO ----
             Sin allowedRoles: aplica a los cuatro roles por igual.
             Registrada antes de las rutas de rol — ProtectedRoute
             redirige acá desde cualquiera de ellas cuando
             user.requiere_cambio_password es true. */}
        <Route path="/cambiar-password-obligatorio"
          element={
            <ProtectedRoute>
              <CambiarPasswordObligatorio />
            </ProtectedRoute>
          }
        />

        {/* ---- CONSUMIDOR ---- */}
        <Route path="/consumidor/solicitud"
          element={
            <ProtectedRoute allowedRoles={["CONS"]}>
              <MiSolicitud />
            </ProtectedRoute>
          }
        />
        <Route path="/consumidor/perfil"
          element={
            <ProtectedRoute allowedRoles={["CONS"]}>
              <MiPerfil />
            </ProtectedRoute>
          }
        />

        {/* ---- ANH / ADMIN ---- */}
        <Route path="/anh/dashboard"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <DashboardANH />
            </ProtectedRoute>
          }
        />
        <Route path="/anh/solicitudes"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <SolicitudesANH />
            </ProtectedRoute>
          }
        />
        <Route path="/anh/solicitudes/:idPublico"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <DetalleSolicitudANH />
            </ProtectedRoute>
          }
        />
        <Route path="/anh/consumidores"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <ConsumidoresANH />
            </ProtectedRoute>
          }
        />
        <Route path="/anh/consumidores/:id"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <DetalleConsumidor />
            </ProtectedRoute>
          }
        />
        <Route path="/anh/estaciones"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <EstacionesANH />
            </ProtectedRoute>
          }
        />
        <Route path="/anh/reportes"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <ReportesANH />
            </ProtectedRoute>
          }
        />
        <Route path="/anh/perfil"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <MiPerfilFuncionario />
            </ProtectedRoute>
          }
        />

        {/* ---- ESS ---- */}
        <Route path="/estacion/solicitudes"
          element={
            <ProtectedRoute allowedRoles={["ESS"]}>
              <SolicitudesESS />
            </ProtectedRoute>
          }
        />
        <Route path="/estacion/historial"
          element={
            <ProtectedRoute allowedRoles={["ESS"]}>
              <HistorialESS />
            </ProtectedRoute>
          }
        />
        <Route path="/estacion/perfil"
          element={
            <ProtectedRoute allowedRoles={["ESS"]}>
              <MiPerfilFuncionario />
            </ProtectedRoute>
          }
        />

        {/* ---- ADMIN ---- */}
        <Route path="/admin/usuarios"
          element={
            <ProtectedRoute allowedRoles={["ADMIN"]}>
              <GestionUsuarios />
            </ProtectedRoute>
          }
        />

        // Ruta para ANH y ADMIN
        <Route path="/admin/registrar-consumidor"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <RegistrarConsumidor />
            </ProtectedRoute>
          }
        />
        <Route path="/anh/estaciones/departamento/:deptoId"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <EstacionesDepartamento />
            </ProtectedRoute>
         }
        />
        <Route path="/anh/estaciones/departamento/:deptoId/provincia/:provId"
          element={
            <ProtectedRoute allowedRoles={["ANH", "ADMIN"]}>
              <EstacionesProvincia />
            </ProtectedRoute>
        }
        />

        {/* ---- FALLBACK ---- */}
        <Route path="*" element={<Navigate to="/" replace />} />

      </Routes>
    </Suspense>
  );
}

// ------------------------------------------------
// APP
// ------------------------------------------------

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}