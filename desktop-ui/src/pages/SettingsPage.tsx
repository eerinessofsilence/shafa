import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { ToggleSwitch } from '../components/ToggleSwitch';
import { surfaceCardClassName } from '../lib/ui';
import type { SettingToggle } from '../types';

interface SettingsPageProps {
  toggles: SettingToggle[];
  onToggleOption: (label: string) => void;
}

export function SettingsPage({
  toggles,
  onToggleOption,
}: SettingsPageProps) {
  return (
    <div className="space-y-4">
      <PageHeader title="Настройки" />

      <div className="grid gap-4">
        <Panel title="Общие параметры">
          <div className="grid grid-cols-2 gap-3">
            {toggles.map((toggle) => (
              <button
                key={toggle.label}
                aria-checked={toggle.enabled}
                className={`${surfaceCardClassName} flex w-full cursor-pointer items-center justify-between gap-3.5 text-left transition-all duration-200 hover:border-border/50 hover:bg-secondary/75 focus:border-info/50 focus:ring-2 focus:ring-info/25`}
                role="switch"
                type="button"
                onClick={() => onToggleOption(toggle.label)}
              >
                <div>
                  <h1 className="font-medium text-text text-lg">
                    {toggle.label}
                  </h1>
                  <span className="leading-6 text-text-muted">
                    {toggle.copy}
                  </span>
                </div>
                <ToggleSwitch checked={toggle.enabled} />
              </button>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
