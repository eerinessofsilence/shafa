import { BarChart3, LayoutGrid, Power, Settings, Users } from 'lucide-react';
import type { ReactNode } from 'react';

import { navItems } from '../data/mockData';
import type { PageId } from '../types';

const navItemIcons: Record<PageId, ReactNode> = {
  dashboard: <LayoutGrid className="h-5 w-5" />,
  accounts: <Users className="h-5 w-5" />,
  parsing: <Power className="h-5 w-5" />,
  stats: <BarChart3 className="h-5 w-5" />,
  settings: <Settings className="h-5 w-5" />,
};

interface AppSidebarProps {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
}

export function AppSidebar({ activePage, onNavigate }: AppSidebarProps) {
  return (
    <aside className="bg-foreground min-h-screen w-full p-5">
      <div className="space-y-4 sticky top-7.5">
        <h1 className="font-semibold text-text tracking-tight text-3xl">
          Shafa Control
        </h1>

        <nav className="flex flex-col gap-2.5">
          {navItems.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2 text-left transition-all duration-200 ${
                activePage === item.id
                  ? 'border border-info/50 bg-secondary text-text'
                  : 'border border-transparent bg-secondary/50 text-text/75 hover:border-border/25 hover:bg-secondary/75'
              }`}
              onClick={() => onNavigate(item.id)}
            >
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-xl transition-colors duration-200 ${
                  activePage === item.id
                    ? 'bg-info/15 text-info'
                    : 'bg-secondary text-text/65'
                }`}
              >
                {navItemIcons[item.id]}
              </span>
              <span className="text-lg font-medium">{item.label}</span>
            </button>
          ))}
        </nav>
      </div>
    </aside>
  );
}
