interface ToggleSwitchProps {
  checked: boolean;
}

export function ToggleSwitch({ checked }: ToggleSwitchProps) {
  return (
    <span
      aria-hidden="true"
      className={`relative inline-flex h-6 w-12 shrink-0 rounded-full border transition-all duration-200 ${
        checked
          ? 'border-success/25 bg-success/20 shadow-[inset_0_0_0_1px_rgba(34,197,94,0.06)]'
          : 'border-border/25 bg-foreground/35'
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 h-4.5 w-4.5 rounded-full shadow-[0_8px_20px_rgba(15,23,42,0.16)] transition-transform duration-200 ${
          checked ? 'translate-x-6 bg-success' : 'bg-white'
        }`}
      />
    </span>
  );
}
