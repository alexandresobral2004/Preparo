import React from "react";

export interface ToastMessage {
  id: number;
  text: string;
  kind: "info" | "error";
}

interface ToastProps {
  toast: ToastMessage | null;
}

export const Toast: React.FC<ToastProps> = ({ toast }) => {
  if (!toast) return null;
  return (
    <div className="toast-container" role="status" aria-live="polite">
      <div className={`toast ${toast.kind === "error" ? "error" : ""}`}>
        {toast.text}
      </div>
    </div>
  );
};
