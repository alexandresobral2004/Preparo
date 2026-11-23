import React, { useEffect, useState } from "react";

interface ConfirmButtonProps {
  label: string;
  confirmLabel?: string;
  onConfirm: () => void;
  className?: string;
  small?: boolean;
  ariaLabel?: string;
  /** Anexado ao nome acessível nos dois estados (ex.: a data do registro), sem mudar o texto visível. */
  contexto?: string;
}

/**
 * Confirmação por segundo toque com expiração automática em 3 segundos (RU-06).
 */
export const ConfirmButton: React.FC<ConfirmButtonProps> = ({
  label,
  confirmLabel = "Toque para confirmar",
  onConfirm,
  className = "",
  small = false,
  ariaLabel,
  contexto,
}) => {
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (!armed) return;
    const timer = window.setTimeout(() => setArmed(false), 3000);
    return () => window.clearTimeout(timer);
  }, [armed]);

  const handleClick = () => {
    if (!armed) {
      setArmed(true);
      return;
    }
    setArmed(false);
    onConfirm();
  };

  return (
    <button
      type="button"
      className={`btn btn-danger ${small ? "btn-sm" : ""} ${armed ? "confirming" : ""} ${className}`}
      onClick={handleClick}
      aria-label={ariaLabel || `${armed ? confirmLabel : label}${contexto ? ` ${contexto}` : ""}`}
    >
      {armed ? confirmLabel : label}
    </button>
  );
};
