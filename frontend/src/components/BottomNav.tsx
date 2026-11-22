import React from "react";
import type { TabKey } from "../types";
import {
  ChacronaLeafIcon,
  FlameIcon,
  NotebookIcon,
  PiIcon,
  PotSteamIcon,
  UserIcon,
} from "./Icons";

interface BottomNavProps {
  activeTab: TabKey;
  onSelect: (tab: TabKey) => void;
  noFogoCount: number;
  registrosCount: number;
  /** Pedidos de entrada aguardando aprovação do dono. */
  contaBadge?: number;
}

export const BottomNav: React.FC<BottomNavProps> = ({
  activeTab,
  onSelect,
  noFogoCount,
  registrosCount,
  contaBadge = 0,
}) => {
  const items: {
    key: TabKey;
    label: string;
    icon: React.ReactNode;
    badge?: number;
    badgeKind?: "fire";
  }[] = [
    { key: "cabecalho", label: "Cabeçalho", icon: <ChacronaLeafIcon /> },
    { key: "panelas", label: "Panelas", icon: <PotSteamIcon /> },
    {
      key: "andamento",
      label: "Andamento",
      icon: <FlameIcon />,
      badge: noFogoCount > 0 ? noFogoCount : undefined,
      badgeKind: "fire",
    },
    {
      key: "registros",
      label: "Registros",
      icon: <NotebookIcon />,
      badge: registrosCount > 0 ? registrosCount : undefined,
    },
    { key: "calc", label: "Calc. π", icon: <PiIcon /> },
    { key: "conta", label: "Conta", icon: <UserIcon />, badge: contaBadge > 0 ? contaBadge : undefined },
  ];

  return (
    <nav className="bottom-nav" aria-label="Menu principal">
      {items.map((item) => {
        const isActive = activeTab === item.key;
        return (
          <button
            key={item.key}
            type="button"
            className={`nav-item ${isActive ? "active" : ""}`}
            onClick={() => onSelect(item.key)}
            aria-current={isActive ? "page" : undefined}
          >
            <span className="nav-icon-wrap">
              {item.icon}
              {item.badge !== undefined && (
                <span className={`nav-badge ${item.badgeKind || ""}`}>
                  {item.badge}
                </span>
              )}
            </span>
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
};
