/// <reference types="vite/client" />

import type { DesktopShellInfo } from "./types";

declare global {
  interface Window {
    desktopShell?: DesktopShellInfo;
  }
}

export {};
