import { useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, Upload, X } from 'lucide-react'
import { upload } from '../../../api/client'
import { Button } from '../../../shared/ui'

export function UploadInvoiceDialog({
  close,
  completed,
}: {
  close: () => void
  completed: () => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [progress, setProgress] = useState(0)
  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error('Choose a PDF first.')
      const form = new FormData()
      form.append('file', file)
      return upload('/documents/upload', form, setProgress)
    },
    onSuccess: completed,
  })
  return (
    <div
      className="ops-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <section className="ops-modal" role="dialog" aria-modal="true" aria-labelledby="upload-title">
        <header>
          <div>
            <h2 id="upload-title">Upload invoice</h2>
            <p>Add one PDF. The system will read it and place it in the correct queue.</p>
          </div>
          <button className="ops-icon-button" onClick={close} aria-label="Close upload">
            <X size={19} />
          </button>
        </header>
        <button className="invoice-dropzone" onClick={() => input.current?.click()}>
          <Upload size={28} />
          <strong>{file ? file.name : 'Choose an invoice PDF'}</strong>
          <span>
            {file ? `${Math.ceil(file.size / 1024)} KB` : 'PDF up to the workspace upload limit'}
          </span>
        </button>
        <input
          ref={input}
          hidden
          type="file"
          accept="application/pdf,.pdf"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        {mutation.isPending ? (
          <div className="upload-progress">
            <span style={{ width: `${progress}%` }} />
            <small>{progress}% uploaded</small>
          </div>
        ) : null}
        {mutation.error ? (
          <p className="ops-form-error">
            <AlertTriangle size={15} />
            {mutation.error.message}
          </p>
        ) : null}
        <footer>
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!file || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            <Upload size={16} /> Upload invoice
          </Button>
        </footer>
      </section>
    </div>
  )
}
