import { forwardRef, type ButtonHTMLAttributes, type PropsWithChildren, type ReactNode } from 'react'
import { AlertCircle, Inbox, LoaderCircle, Search, X } from 'lucide-react'

export function PageHeader({ title, description, action, eyebrow }: { title: string; description?: string; action?: ReactNode; eyebrow?: string }) {
  return <header className="ops-page-header">
    <div>{eyebrow ? <span className="ops-eyebrow">{eyebrow}</span> : null}<h1>{title}</h1>{description ? <p>{description}</p> : null}</div>
    {action ? <div className="ops-page-action">{action}</div> : null}
  </header>
}

export function Panel({ children, className = '', ariaLabel }: PropsWithChildren<{ className?: string; ariaLabel?: string }>) {
  return <section className={`ops-panel ${className}`.trim()} aria-label={ariaLabel}>{children}</section>
}

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' | 'ghost' }>(function Button({ variant = 'secondary', className = '', children, ...props }, ref) {
  return <button ref={ref} className={`ops-button ops-button--${variant} ${className}`.trim()} {...props}>{children}</button>
})

export function StatusBadge({ tone = 'neutral', children }: PropsWithChildren<{ tone?: 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'purple' }>) {
  return <span className={`ops-badge ops-badge--${tone}`}>{children}</span>
}

export function SearchField({ value, onChange, placeholder = 'Search...', label = 'Search' }: { value: string; onChange: (value: string) => void; placeholder?: string; label?: string }) {
  return <label className="ops-search"><span className="sr-only">{label}</span><Search size={17} aria-hidden="true" /><input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />{value ? <button type="button" onClick={() => onChange('')} aria-label="Clear search"><X size={15} /></button> : null}</label>
}

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return <div className="ops-state" role="status"><LoaderCircle className="spin" size={24} /><strong>{label}</strong></div>
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return <div className="ops-state"><Inbox size={26} /><strong>{title}</strong><span>{body}</span>{action}</div>
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="ops-state ops-state--error" role="alert"><AlertCircle size={26} /><strong>{message}</strong>{retry ? <Button onClick={retry}>Try again</Button> : null}</div>
}

export function KpiCard({ label, value, note, icon, tone = 'info' }: { label: string; value: ReactNode; note?: ReactNode; icon: ReactNode; tone?: 'info' | 'success' | 'warning' | 'danger' | 'purple' }) {
  return <Panel className="ops-kpi"><span className={`ops-kpi__icon ops-tone-${tone}`}>{icon}</span><div><span>{label}</span><strong>{value}</strong>{note ? <small>{note}</small> : null}</div></Panel>
}

export function SkeletonRows({ count = 5 }: { count?: number }) {
  return <div className="ops-skeleton-list" aria-label="Loading data">{Array.from({ length: count }, (_, index) => <span key={index} />)}</div>
}
