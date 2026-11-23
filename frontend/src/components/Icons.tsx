import React from "react";

interface IconProps {
  size?: number;
}

export const ChacronaLeafIcon: React.FC<IconProps> = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 19C5 10.5 11 4.5 19.5 4.5C19.5 13 13.5 19 5 19Z" />
    <path d="M5 19L15 9" />
    <path d="M9.5 14.5L9.5 10.5" />
    <path d="M12.5 11.5L16.5 11.5" />
  </svg>
);

export const PotSteamIcon: React.FC<IconProps> = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M8.5 3.5C8.5 5 9.5 5.5 9.5 7" />
    <path d="M12 2.5C12 4.3 13 4.8 13 6.8" />
    <path d="M15.5 3.5C15.5 5 16.5 5.5 16.5 7" />
    <path d="M4 10H20" />
    <path d="M2.5 11.5H4.5" />
    <path d="M19.5 11.5H21.5" />
    <path d="M5.5 10H18.5V16.5C18.5 18.7 16.7 20.5 14.5 20.5H9.5C7.3 20.5 5.5 18.7 5.5 16.5V10Z" />
  </svg>
);

export const FlameIcon: React.FC<IconProps> = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12.2 2.8C12.2 2.8 18 7.5 18 13.2C18 17.1 15.3 20.5 12 20.5C8.7 20.5 6 17.5 6 13.8C6 11.1 7.6 8.5 9.1 7C9.1 9.1 10.3 10.1 11 10.2C10.5 7.4 12.2 2.8 12.2 2.8Z" />
  </svg>
);

export const NotebookIcon: React.FC<IconProps> = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="6" y="3.5" width="13.5" height="17" rx="2" />
    <path d="M4 7.5H7.5" />
    <path d="M4 12H7.5" />
    <path d="M4 16.5H7.5" />
    <path d="M10.5 8.5H16" />
    <path d="M10.5 12.5H16" />
    <path d="M10.5 16.5H14" />
  </svg>
);

export const PiIcon: React.FC<IconProps> = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M4.5 7H19.5" />
    <path d="M9 7V18.5" />
    <path d="M15.5 7V15.8C15.5 17.5 16.5 18.5 18.2 18.5C19 18.5 19.6 18.2 20 17.8" />
  </svg>
);

export const SunIcon: React.FC<IconProps> = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2V4M12 20V22M4.9 4.9L6.3 6.3M17.7 17.7L19.1 19.1M2 12H4M20 12H22M4.9 19.1L6.3 17.7M17.7 6.3L19.1 4.9" />
  </svg>
);

export const MoonIcon: React.FC<IconProps> = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5A8.5 8.5 0 1 0 20.5 14.5Z" />
  </svg>
);

export const LogOutIcon: React.FC<IconProps> = ({ size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <path d="m16 17 5-5-5-5" />
    <path d="M21 12H9" />
  </svg>
);

export const PencilIcon: React.FC<IconProps> = ({ size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z" />
    <path d="m15 5 4 4" />
  </svg>
);

export const UserIcon: React.FC<IconProps> = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="8" r="4" />
    <path d="M4.5 20.5c0-4 3.4-6.5 7.5-6.5s7.5 2.5 7.5 6.5" />
  </svg>
);
