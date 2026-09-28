// src/components/ui/EnlaceEnviadoModal.tsx

import { Modal } from "./Modal";
import { Button } from "./Button";
import { Alert } from "./Alert";
import { Mail, Info, Send } from "lucide-react";

type TipoEnlace = "activacion" | "recuperacion";

interface Props {
  open:          boolean;
  onClose:       () => void;
  titulo:        string;
  email:         string;
  emailEnviado:  boolean;
  tipo:          TipoEnlace;
  // Si el email no salió, se ofrece reintentar desde el mismo modal.
  onReenviar?:   () => void;
  reenviando?:   boolean;
  className?:    string;
}

const textos: Record<TipoEnlace, { enviado: string; fallo: string; nota: string }> = {
  activacion: {
    enviado: "Se envió un enlace de activación a",
    fallo:   "La cuenta se creó, pero no se pudo enviar el email de activación. Reenvía el enlace.",
    nota:    "El usuario debe abrir el enlace y crear su contraseña para activar la cuenta. El enlace vence en 72 horas.",
  },
  recuperacion: {
    enviado: "Se envió un enlace para crear una nueva contraseña a",
    fallo:   "La contraseña se reseteó, pero no se pudo enviar el email. Vuelve a intentarlo.",
    nota:    "La contraseña anterior ya no es válida y se cerraron las sesiones del usuario.",
  },
};

// Reemplaza al antiguo modal de contraseña provisional: ningún flujo
// de alta o reset muestra contraseñas, el usuario define la suya
// desde el link que recibe por email.
export function EnlaceEnviadoModal({
  open, onClose, titulo, email, emailEnviado, tipo,
  onReenviar, reenviando = false, className = "",
}: Props) {
  const t = textos[tipo];

  return (
    <Modal open={open} onClose={onClose} title={titulo} size="md">
      <div className={`space-y-4 ${className}`}>
        {emailEnviado ? (
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-full bg-state-success-bg flex items-center justify-center shrink-0">
              <Mail className="w-5 h-5 text-state-success-fg" />
            </div>
            <p className="text-sm text-foreground pt-2">
              {t.enviado} <strong>{email}</strong>.
            </p>
          </div>
        ) : (
          <Alert type="warning" message={t.fallo} />
        )}

        <div className="flex items-start gap-2 text-xs text-muted-foreground">
          <Info className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{t.nota}</span>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          {!emailEnviado && onReenviar && (
            <Button variant="outline" icon={<Send className="w-4 h-4" />}
              loading={reenviando} onClick={onReenviar}>
              Reenviar enlace
            </Button>
          )}
          <Button variant="primary" onClick={onClose}>Entendido</Button>
        </div>
      </div>
    </Modal>
  );
}
