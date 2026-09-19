import {
  useEffect,
  useRef,
  type ReactNode,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
} from "react";
import {
  AlertCircle,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  Inbox,
  X,
} from "lucide-react";
import { human } from "../api";
export function Button({
  children,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return (
    <button {...props} className={`button ${variant} ${props.className || ""}`}>
      {children}
    </button>
  );
}
export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`input ${props.className || ""}`} />;
}
export function Select({
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className="input select">
      {children}
    </select>
  );
}
export function Badge({
  children,
  status,
}: {
  children?: ReactNode;
  status?: string;
}) {
  return (
    <span className={`badge ${status?.toLowerCase() || ""}`}>
      <span className="status-dot" />
      {children || human(status || "")}
    </span>
  );
}
export function Skeleton() {
  return (
    <div className="skeleton-stack" aria-label="Loading">
      <div className="skeleton title" />
      <div className="skeleton" />
      <div className="skeleton" />
      <div className="skeleton" />
    </div>
  );
}
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Inbox size={30} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: Error | null;
  retry?: () => void;
}) {
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={18} />
      <span>{error?.message || "Something went wrong"}</span>
      {retry && (
        <Button variant="ghost" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog ref={ref} onCancel={onClose} className="modal">
      <header>
        <h2>{title}</h2>
        <Button variant="ghost" onClick={onClose} aria-label="Close">
          <X size={18} />
        </Button>
      </header>
      {children}
    </dialog>
  );
}
export function Drawer(props: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="drawer">
      <Modal {...props} />
    </div>
  );
}
export function Tabs({
  tabs,
  value,
  onChange,
}: {
  tabs: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          role="tab"
          aria-selected={t === value}
          className={t === value ? "active" : ""}
          key={t}
          onClick={() => onChange(t)}
        >
          {t}
        </button>
      ))}
    </div>
  );
}
export function Tooltip({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return <span title={label}>{children}</span>;
}
export function Dropdown({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <details className="dropdown">
      <summary>{label}</summary>
      <div>{children}</div>
    </details>
  );
}
export function Table({
  headers,
  children,
}: {
  headers: string[];
  children: ReactNode;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
export function Pagination({
  page,
  total,
  pageSize,
  onChange,
}: {
  page: number;
  total: number;
  pageSize: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total
          ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)}`
          : "0"}{" "}
        of {total} tasks
      </span>
      <div>
        <Button
          variant="ghost"
          disabled={page === 1}
          onClick={() => onChange(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </Button>
        <span>Page {page}</span>
        <Button
          variant="ghost"
          disabled={page * pageSize >= total}
          onClick={() => onChange(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
export function MetricCard({
  label,
  value,
  caption,
  icon,
}: {
  label: string;
  value: number;
  caption: string;
  icon: ReactNode;
}) {
  return (
    <div className="metric">
      <div>
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value.toLocaleString()}</strong>
      <small>{caption}</small>
    </div>
  );
}
export function JsonViewer({ value }: { value: unknown }) {
  return (
    <div className="json-viewer">
      <button
        title="Copy JSON"
        aria-label="Copy JSON"
        onClick={() =>
          navigator.clipboard?.writeText(JSON.stringify(value, null, 2))
        }
      >
        <Copy size={13} />
      </button>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}
export function Toast({
  message,
  onClose,
}: {
  message: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);
  return (
    <div className="toast" role="status">
      <Check size={16} />
      {message}
      <button aria-label="Dismiss notification" onClick={onClose}>
        <X size={14} />
      </button>
    </div>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function SectionLink({ children }: { children: ReactNode }) {
  return (
    <span className="section-link">
      {children}
      <ArrowRight size={14} />
    </span>
  );
}
