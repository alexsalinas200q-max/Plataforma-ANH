// src/types/consumidor.types.ts

export type EstadoIdentidad =
  | "PENDIENTE"
  | "EN_REVISION"
  | "VERIFICADO"
  | "RECHAZADO";

export type EstadoAlerta =
  | "NORMAL"
  | "EN_REVISION"
  | "BLOQUEADO";

export type ActividadEconomica =
  | "AGRICULTURA"
  | "TRANSPORTE"
  | "INDUSTRIA"
  | "PESCA"
  | "CONSTRUCCION"
  | "DOMESTICO"
  | "COMERCIO"
  | "MINERIA"
  | "OTRO";

export interface DocumentoIdentidad {
  id:                    number;
  tipo_documento:        "CI" | "CIE";
  tipo_documento_display: string;
  numero_documento:      string;
  complemento_documento: string;
  anverso:               string;
  reverso:               string;
  foto_sosteniendo:      string | null;
  fecha_subida:          string;
}

export interface ConsumidorPerfil {
  id:                       number;
  user: {
    id:              number;
    email:           string;
    nombres:         string;
    apellido_paterno: string;
    apellido_materno: string;
    estado_cuenta:   "PENDIENTE" | "ACTIVO" | "SUSPENDIDO";
  };
  fecha_nacimiento:         string;
  celular:                  string;
  celular_verificado:       boolean;
  departamento:             number | null;
  departamento_nombre:      string;
  provincia:                number | null;
  provincia_nombre:         string;
  municipio:                number | null;
  municipio_nombre:         string;
  direccion:                string;
  actividad:                ActividadEconomica | "";
  actividad_display:        string;
  estado_identidad:         EstadoIdentidad;
  estado_identidad_display: string;
  alerta_repetitividad:     EstadoAlerta;
  alerta_display:           string;
  fecha_alerta:             string | null;
  motivo_bloqueo:           string;
  documentos:               DocumentoIdentidad[];
  fecha_creacion:           string;
}

// ------------------------------------------------
// CATÁLOGOS
// ------------------------------------------------

// Fila del listado GET /api/consumidores/ (ConsumidorPerfilListSerializer)
export interface ConsumidorListItem {
  id:                   number;
  nombre_completo:      string;
  email:                string;
  estado_identidad:     EstadoIdentidad;
  alerta_repetitividad: EstadoAlerta;
  municipio_nombre:     string;
  fecha_creacion:       string;
}

export interface Departamento {
  id:     number;
  nombre: string;
  codigo: string;
}

export interface Provincia {
  id:     number;
  nombre: string;
  codigo: string;
}

export interface Municipio {
  id:     number;
  nombre: string;
  codigo: string;
}