# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ANH Bolivia — sistema de gestión de solicitudes de combustible subvencionado. Monorepo con dos proyectos independientes:

- `backend/` — Django REST Framework API
- `frontend/` — React + TypeScript SPA (Vite)

## Commands

### Backend (`backend/`)

```bash
python manage.py runserver          # dev server (http://127.0.0.1:8000)
python manage.py migrate            # apply migrations
python manage.py makemigrations     # create migrations after model changes
python manage.py test               # run all tests
python manage.py test solicitudes   # run tests for one app
python manage.py test solicitudes.tests.ClassName.test_method  # single test
python manage.py expirar_solicitudes  # expira/rechaza solicitudes vencidas (ver "solicitudes/" abajo)
python manage.py createsuperuser
```

Requires a `.env` file in `backend/` (not committed) with at least `DJANGO_SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`. Database is PostgreSQL — there's no SQLite fallback configured.

### Frontend (`frontend/`)

```bash
npm run dev       # dev server (http://127.0.0.1:5173)
npm run build     # tsc -b && vite build
npm run lint      # eslint .
npm run preview   # preview production build
```

No test runner is configured in `frontend/package.json`.

## Architecture

### Backend — Django apps

Located in `backend/`, one directory per app, standard Django layout (`models.py`, `serializers.py`, `views.py`, `urls.py`, `permissions.py`, `migrations/`) plus project-specific additions:

- **`core/`** — project settings/urls/wsgi/asgi. Not a Django "app" with models.
- **`users/`** — custom `User` model (`AUTH_USER_MODEL = "users.User"`), authentication (login/refresh/logout, email verification via PIN, password recovery), and the RBAC permission base classes every other app builds on (`permissions.py`). Also owns `email_service.py` (Brevo HTTP API in prod, console backend in dev) and `authentication.py` (`CookieJWTAuthentication`).
- **`consumidores/`** — consumer profile and identity documents.
- **`estaciones/`** — gas stations (estaciones de servicio) CRUD and status.
- **`solicitudes/`** — the core domain: fuel request lifecycle. Business logic lives in **`services/`** (one file per operation: `aprobar_solicitud.py`, `rechazar_solicitud.py`, `despachar_solicitud.py`, `observar_solicitud.py`, `generar_comprobante.py`, `generar_declaracion_jurada.py`, `verificar_repetitividad.py`, `registrar_auditoria.py`, report generators) rather than in `views.py` — views call into these services. Expiration of overdue requests (APROBADA → EXPIRADA, OBSERVADA past its 24 h → RECHAZADA) lives in `services/expirar_solicitudes.py` and runs two ways: the `expirar_solicitudes` management command, scheduled in production as a Railway Cron service every 10 minutes, and a lazy fallback (`expirar_solicitudes_vencidas_seguro()`, 5-minute per-worker guard) called from the list, dashboard and statistics views. There is no `cron.py`/`runcrons` (django-cron was never installed). Rejection emails are sent via `transaction.on_commit`, never inside the locked transaction. Also has `views_dashboard.py`, `views_estadisticas.py`, `views_reportes.py` as separate view modules beyond the default `views.py`, and `filters.py` for `django-filter` querysets.
- **`configuracion/`** and **`catalogos/`** — app-wide settings and reference/lookup data (catálogos have `fixtures/`).

Routing (`core/urls.py`) mounts apps under `/api/<app>/...` and documents the generated routes inline as comments above each `include()`. When adding endpoints, follow that same comment convention.

### Auth model

JWT via `djangorestframework_simplejwt`, but tokens travel as **httponly cookies** (`access_token` / `refresh_token`), not just headers — see `CookieJWTAuthentication` in `users/authentication.py`, which reads the cookie and falls back to the `Authorization: Bearer` header. Access token lifetime is 30 min, refresh 1 day, with rotation + blacklisting enabled. Cookie `SameSite` is `Lax` in dev and `None` (cross-site, frontend on Vercel / backend on Railway) in production.

### Roles / permissions

Four roles on `User.TipoUsuario`: `ADMIN`, `ANH`, `ESS` (estación de servicio), `CONS` (consumidor). `users/permissions.py` defines the base classes (`IsAuthenticatedActive` → `HasRole` → `IsAdmin`, `IsANH`, `IsAdminOrANH`, `IsESS`, `IsConsumidor`, `IsAdminOrANHOrESS`); other apps subclass these per-view/per-object rather than checking roles inline (e.g. `solicitudes/permissions.py` wraps them as `EsConsumidor`, `EsUsuarioANH`, `EsEstacionAsignada` with object-level checks). Follow this pattern for any new role-gated endpoint instead of writing ad hoc role checks in views.

### Deployment

Frontend deploys to Vercel (`vercel.json`), backend to Railway (`Procfile`: gunicorn + `migrate` on release, `whitenoise` for static files, `dj-database-url`/`DATABASE_URL` when present, else discrete `DB_*` env vars).

### Frontend structure (`frontend/src/`)

- **`context/AuthContext.tsx`** — owns the single axios instance (`export const api`), auth state, and the token-refresh interceptor. All API calls should reuse this `api` instance (see `services/*.service.ts`), not create their own axios client. Access token is kept in memory + `localStorage`; refresh happens transparently on a 401 via `/api/users/auth/refresh/` (excluded from retry: login/refresh/logout URLs themselves).
- **`services/*.service.ts`** — one file per backend app, thin wrappers around `api.get/post/...` returning typed responses. This is the only layer that should call `api` directly from page code.
- **`pages/`** — routed screens, split by role: `admin/`, `anh/`, `consumidor/`, `estacion/`, plus top-level public pages (`Login.tsx`, `RecuperarPassword.tsx`, etc.). Role-specific pages are lazy-loaded in `App.tsx`.
- **`App.tsx`** — all routing lives here. Routes are wrapped in `<ProtectedRoute allowedRoles={[...]}>`; `RoleRedirect` sends an authenticated user from `/` to their role's home page (`tipo_usuario` → route mapping mirrors the backend's `TipoUsuario` choices).
- **`components/ui/`** — the shared component kit (see below).
- **`types/`** and **`utils/constants.ts`** — TS types and shared enums/labels mirroring backend choices (e.g. `ESTADOS_SOLICITUD`, `ESTADOS_IDENTIDAD`, `ALERTAS_CONSUMIDOR` label/color maps consumed by `EstadoBadge.tsx`).

### `src/components/ui/` conventions

Plain function components, no UI library (no shadcn/radix) — every component is hand-rolled and small:

- Props typed with a local `interface Props` (or `<Name>Props` for larger components like `Button`), `children?: ReactNode`, and always a `className = ""` passthrough appended last in the class string so callers can override/extend styles.
- Variant/size styling is done via `Record<string, string>` lookup objects (`variants`, `sizes`) keyed by a prop, not `clsx`/`cva` or conditional ternary chains — follow this table pattern when adding a new variant.
- File header comment is just the relative path, e.g. `// src/components/ui/Button.tsx`.
- Compound components live in one file and are exported individually (e.g. `Card`, `CardHeader`, `CardBody` all in `Card.tsx`).
- Icons come from `lucide-react`.
- Domain-specific badges (`EstadoBadge.tsx`) wrap the generic `Badge` and look up label/color from the `utils/constants.ts` maps rather than hardcoding strings — extend those maps, don't add new badge components for new statuses.

### Tailwind setup and palette

Tailwind v4 (`@tailwindcss/vite` plugin, no `tailwind.config.js`). The theme is defined with CSS custom properties in an `@theme` block in `src/index.css` — **add new design tokens there**, not by hardcoding hex values in components. Current semantic tokens (used as `bg-*`/`text-*`/`border-*` utilities):

| Token | Value | Usage |
|---|---|---|
| `navbar`, `navbar-foreground`, `navbar-muted` | `#17212B` / `#FFFFFF` / `#94A3B8` | top navigation bar |
| `primary`, `primary-hover`, `primary-foreground` | `#10B981` / `#059669` / `#FFFFFF` | brand green, primary actions |
| `background` | `#F8FAFC` | page background |
| `card` | `#FFFFFF` | `Card`, `Modal` surfaces |
| `foreground` | `#111827` | primary text |
| `muted-foreground` | `#6B7280` | secondary text |
| `border` | `#E5E7EB` | `border-border` on cards/dividers/inputs |
| `input` | `#F8FAFC` | form input background |
| `ring` | `#10B981` | focus rings |
| `state-pending-bg` / `state-pending-fg` | `#FEF3C7` / `#92400E` | pending badges |
| `state-success-bg` / `state-success-fg` | `#D1FAE5` / `#065F46` | success/approved badges |
| `state-warning-bg` / `state-warning-fg` | `#FFEDD5` / `#9A3412` | warning/observed badges |
| `state-danger-bg` / `state-danger-fg` | `#FEE2E2` / `#991B1B` | danger/rejected badges |

The `state-*` pairs exist specifically for status badges (`EstadoBadge.tsx`, `Stepper.tsx`) — use them for any new status/estado UI instead of raw Tailwind colors (`bg-red-100`, etc.), which only appear as one-off exceptions (e.g. `Button`'s `danger` variant currently uses `bg-red-600`).

## Working guidelines

- Respond in Spanish.
- Before writing code that references model fields, serializer
  fields, or API response shapes, read the actual file. Do not
  infer field names from context or from the frontend types.
- When a page needs a new status color, extend the `state-*`
  tokens in `index.css` and the label/color maps in
  `utils/constants.ts`. Do not use raw Tailwind colors
  (`bg-red-100`, `bg-amber-500`) for status UI.
- Alerts and success messages auto-dismiss after 4s via a
  `flash()` helper backed by a `useRef` timer. Follow that
  pattern instead of leaving messages pinned.
- Tables: rows are clickable (navigate on row click, ChevronRight
  on hover). Do not add a separate "Ver" button column.
- Status filters are horizontal tabs, not dropdowns.
- Back navigation uses `navigate(-1)`, never a hardcoded route.
- Prefer editing existing files over creating new ones.
- Do not commit unless explicitly asked.

## Current work

Branch `feature/rediseno-ess` — ESS role redesign, plus a pass on
ANH/ADMIN panels and shared password/reset flows. Not yet merged
to `main`; working tree has uncommitted changes on top of the
last commit (`b19f59f`, "Historial de despachos ESS + limpieza de
tokens de color").

Done:
- ESS dispatch view (`pages/estacion/Solicitudes.tsx`) and
  dispatch history page (`pages/estacion/Historial.tsx`).
- ANH/ADMIN panel redesign (`pages/anh/*`,
  `pages/admin/GestionUsuarios.tsx`) and admin-driven consumer
  registration (`pages/admin/RegistrarConsumidor.tsx`).
- Password reset/change flow: `CambiarPasswordModal.tsx` +
  `MostrarPasswordModal.tsx` (shows a one-time temporary
  password), `pages/CambiarPasswordObligatorio.tsx` (forced
  change on first login), `pages/MiPerfilFuncionario.tsx`
  (profile page for ANH/ADMIN/ESS users with password change —
  covers the "ESS profile page" item from the original plan).
- Solicitud lifecycle: dispatch/reject services updated
  (`despachar_solicitud.py`, `rechazar_solicitud.py`), new
  `expirar_solicitudes.py` service replacing the old
  `solicitudes/cron.py` (deleted — logic moved into the service +
  the existing `expirar_solicitudes` management command),
  `observacion_despacho` migration (0006) for recording dispatch
  observations.
- Case-insensitive email uniqueness for users (migration 0002 in
  `users/`).

Not yet committed / in progress — review before committing:
- Backend changes across `solicitudes`, `users`, `consumidores`,
  `estaciones` (see `git status` for the full list) don't have a
  commit yet.
- `backend/users/management/` is new and untracked — check its
  contents are intentional before adding.

Next:
- Audit timeline for `pages/anh/DetalleSolicitud.tsx` — show
  `AuditoriaEstadoSolicitud` history (despachar/rechazar/cancelar/
  expirar) reusing `EstadoBadge`/`ESTADOS_SOLICITUD`; open question
  on whether to surface `ip_address`.
- Work through the Known issues list below.

## Known issues

### Alta prioridad
- **Reportes: rango de fechas inválido.** El filtro "desde/hasta"
  en Reportes permite `desde > hasta` y deja descargar archivos
  vacíos sin avisar. Falta validar el rango antes de pedir el
  reporte (`services/reportes.service.ts`,
  `solicitudes/views_reportes.py`).
- **Manejo de errores de red silencioso.** Varias pantallas
  atrapan errores de fetch con `.catch(() => {})` y quedan con
  selects/listas vacías sin ningún mensaje al usuario. Reemplazar
  por el patrón `flash()` de error en cada pantalla afectada
  (identificar todas al auditar, no solo una).

### Media prioridad
- **Cupo mensual: error silencioso en `/mi-disponible/`.** Si falla
  el fetch del cupo (`refreshCupo` en `context/AuthContext.tsx`),
  el error se descarta: `CupoMensualWidget` no se muestra y el
  formulario de `MiSolicitud.tsx` cae al máximo de 120 L, sin
  mensaje al usuario. No rompe nada (el backend valida el cupo
  igual), pero es un caso más del manejo de errores silencioso de
  arriba — resolver con el mismo patrón `flash()`.
- **Presentación de datos en reportes PDF/Excel** necesita mejoras
  (formato, layout) — sin detalle todavía de qué específicamente,
  revisar con el usuario.
- **Expiración de solicitudes: falta verificar el Cron en
  producción.** La lógica (`solicitudes/services/expirar_solicitudes.py`)
  corre con el management command `expirar_solicitudes` (servicio Cron
  de Railway cada 10 min) y, como respaldo, de forma perezosa desde los
  listados. Falta confirmar end-to-end en Railway que el servicio Cron
  corre y termina (logs "Nada para expirar…" / conteos).

### Baja prioridad
- **Ajustes de responsive en móvil** — pendientes, menores.

### Resueltos
- **Reset de contraseña mostraba la contraseña en texto plano** —
  resuelto en H1 (`3aa3bd0`): alta y reset por ADMIN/ANH envían un
  link por email; `MostrarPasswordModal.tsx` eliminado.
- **Brevo sin configurar** — operativo en producción
  (`FRONTEND_URL=https://plataforma-anh.vercel.app` verificada).

Known issues tracked here going forward — ask before assuming
something is a bug vs. intentional if it's not on this list.

## Deuda técnica

Subcomponentes definidos dentro del cuerpo de renderizado de un
componente padre (en vez de como componentes de nivel superior) —
evitar este patrón en código nuevo, y corregir oportunistamente en
estos archivos cuando se los toque:

- `frontend/src/pages/estacion/Solicitudes.tsx`
- `frontend/src/pages/estacion/Historial.tsx`
- `frontend/src/pages/anh/Dashboard.tsx`