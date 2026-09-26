import { ChevronDown, ChevronUp } from "lucide-react";

interface Props {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

export default function CollapsibleSection({ title, open, onToggle, children }: Props) {
  return (
    <section className="mt-8">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between py-1 text-left"
        aria-expanded={open}
      >
        <h2 className="text-sm font-semibold" style={{ color: "var(--ink)" }}>{title}</h2>
        <span style={{ color: "var(--ink-soft)" }}>
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </span>
      </button>
      {open && <div className="mt-3">{children}</div>}
    </section>
  );
}
