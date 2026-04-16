/// <reference types="vite/client" />

import type { DesktopShellInfo } from './types';

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

declare global {
  interface Window {
    desktopShell?: DesktopShellInfo;
  }
}

export {};
