import { useEffect } from 'react'
import { AlertCircle, Check, LoaderCircle } from 'lucide-react'
import { Button } from '../../../shared/ui'
import type { DecisionKind } from '../selectors'

export function DecisionModal({
  kind,
  invoice,
  issue,
  note,
  pending,
  error,
  cancel,
  confirm,
  confirmRef,
}: {
  kind: DecisionKind
  invoice: string
  issue?: string
  note: string
  pending: boolean
  error: Error | null
  cancel: () => void
  confirm: () => void
  confirmRef: React.RefObject<HTMLButtonElement | null>
}) {
  const title =
    kind === 'approve'
      ? 'Approve invoice?'
      : kind === 'reject'
        ? 'Reject invoice?'
        : 'Request correction?'
  useEffect(() => {
    confirmRef.current?.focus()
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) cancel()
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [cancel, confirmRef, pending])
  return (
    <div
      className="ops-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) cancel()
      }}
    >
      <section
        className="ops-modal review-confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="decision-confirm-title"
      >
        <header>
          <div>
            <h2 id="decision-confirm-title">{title}</h2>
            <p>This action will be recorded in the audit trail.</p>
          </div>
        </header>
        <dl>
          <div>
            <dt>Invoice</dt>
            <dd>{invoice}</dd>
          </div>
          {issue ? (
            <div>
              <dt>Issue</dt>
              <dd>{issue}</dd>
            </div>
          ) : null}
          {note ? (
            <div>
              <dt>Decision note</dt>
              <dd>{note}</dd>
            </div>
          ) : null}
        </dl>
        {error ? (
          <p className="review-inline-error">
            <AlertCircle size={14} />
            {error.message} Your note has been preserved.
          </p>
        ) : null}
        <footer>
          <Button disabled={pending} onClick={cancel}>
            Cancel
          </Button>
          <Button
            ref={confirmRef}
            variant={kind === 'approve' ? 'primary' : 'danger'}
            disabled={pending}
            onClick={confirm}
          >
            {pending ? (
              <LoaderCircle className="spin" size={16} />
            ) : kind === 'approve' ? (
              <Check size={16} />
            ) : (
              <AlertCircle size={16} />
            )}{' '}
            {pending
              ? 'Saving decision...'
              : kind === 'approve'
                ? 'Approve'
                : kind === 'reject'
                  ? 'Reject'
                  : 'Request correction'}
          </Button>
        </footer>
      </section>
    </div>
  )
}
