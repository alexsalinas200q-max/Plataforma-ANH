// src/utils/format.ts

export const formatFecha = (fecha: string | null, conHora = false): string => {
  if (!fecha) return "—";
  const d = new Date(fecha);
  const opciones: Intl.DateTimeFormatOptions = {
    day:   "2-digit",
    month: "2-digit",
    year:  "numeric",
    ...(conHora && { hour: "2-digit", minute: "2-digit" }),
  };
  return d.toLocaleDateString("es-BO", opciones);
};

// Fecha LOCAL del navegador como YYYY-MM-DD, para filtros "hoy" /
// "desde" que se mandan al backend. No usar toISOString().slice(0, 10):
// devuelve la fecha UTC, que en La Paz (UTC-4) ya es "mañana" desde
// las 20:00.
export const fechaLocalISO = (d: Date = new Date()): string => {
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mes}-${dia}`;
};

export const formatLitros = (litros: number | null): string => {
  if (litros === null || litros === undefined) return "—";
  return `${litros} L`;
};

export const formatIdPublico = (id: string): string =>
  id.slice(0, 8).toUpperCase();

