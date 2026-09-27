// src/components/ui/CupoMensualWidget.tsx

import { Fuel } from "lucide-react";

interface Props {
  usado:      number;
  total:      number;
  disponible: number;
  className?: string;
}

// Verde <70%, amarillo 70-90%, rojo >90% del cupo mensual — mismos
// tokens state-* que EstadoBadge/Stepper, no colores Tailwind sueltos.
function colorPorPorcentaje(pct: number) {
  if (pct > 90) return { barra: "bg-state-danger-fg",  texto: "text-state-danger-fg"  };
  if (pct >= 70) return { barra: "bg-state-warning-fg", texto: "text-state-warning-fg" };
  return { barra: "bg-state-success-fg", texto: "text-state-success-fg" };
}

export function CupoMensualWidget({ usado, total, disponible, className = "" }: Props) {
  const porcentaje = total > 0 ? Math.min(100, Math.round((usado / total) * 100)) : 0;
  const { barra, texto } = colorPorPorcentaje(porcentaje);

  return (
    <div className={`bg-card rounded-2xl border border-border shadow-sm px-5 py-4 ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Fuel className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">Consumo del mes</span>
        </div>
        <span className={`text-sm font-semibold ${texto}`}>
          {usado} / {total} L ({porcentaje}%)
        </span>
      </div>
      <div className="w-full bg-background rounded-full h-2 overflow-hidden">
        <div
          className={`h-2 rounded-full transition-all ${barra}`}
          style={{ width: `${porcentaje}%` }}
        />
      </div>
      <p className="text-xs text-muted-foreground mt-1.5">
        Disponible: <strong className="text-foreground">{disponible} L</strong> este mes
      </p>
    </div>
  );
}
