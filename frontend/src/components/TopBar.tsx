import React from "react";
import type { TabKey } from "../types";
import { formatDateBr } from "../domain/format";
import { MoonIcon, SunIcon } from "./Icons";

interface TopBarProps {
  tab: TabKey;
  dataPreparo: string;
  mestre: string;
  online: boolean;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onSave: () => void;
  saving: boolean;
}

const TITLES: Record<TabKey, string> = {
  cabecalho: "Cabeçalho",
  panelas: "Panelas",
  andamento: "Andamento",
  registros: "Registros",
  calc: "Calculadora π",
  conta: "Conta",
};

export const TopBar: React.FC<TopBarProps> = ({
  tab,
  dataPreparo,
  mestre,
  online,
  theme,
  onToggleTheme,
  onSave,
  saving,
}) => {
  const showSave = tab === "cabecalho" || tab === "panelas";
  const subtitle = `Preparo de ${formatDateBr(dataPreparo)}${mestre.trim() ? ` · ${mestre.trim()}` : ""}`;

  return (
    <header className="topbar">
      <div className="topbar-title-group">
        <h1 className="topbar-title">{TITLES[tab]}</h1>
        <div className="topbar-subtitle">
          <span>{subtitle}</span>
          <span className={`sync-dot ${online ? "" : "offline"}`}>
            {online ? "SQLite" : "Offline"}
          </span>
        </div>
      </div>

      <div className="topbar-actions">
        <button
          type="button"
          className="btn btn-icon"
          onClick={onToggleTheme}
          aria-label={theme === "dark" ? "Mudar para tema claro" : "Mudar para tema escuro"}
          title={theme === "dark" ? "Tema claro" : "Tema escuro"}
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>

        {showSave && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={onSave}
            disabled={saving}
          >
            {saving ? "Salvando..." : "Salvar"}
          </button>
        )}
      </div>
    </header>
  );
};
