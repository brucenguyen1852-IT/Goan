/**
 * Vài thành phần dùng chung. Sẽ tách ra `packages/ui` khi Partner Portal cần dùng lại (P1-14).
 */
import type { ReactNode } from "react";

export function Card({ title, action, children }: { title?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      {(title || action) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Badge({ kind, children }: { kind?: "ok" | "warn" | "bad" | "muted"; children: ReactNode }) {
  return <span className={`badge badge-${kind ?? "muted"}`}>{children}</span>;
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function ErrorText({ children }: { children: ReactNode }) {
  return children ? <p className="error">{children}</p> : null;
}

export function Button({
  children,
  onClick,
  kind = "default",
  disabled,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  kind?: "default" | "primary" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button className={`btn btn-${kind}`} onClick={onClick} disabled={disabled} type={type}>
      {children}
    </button>
  );
}
