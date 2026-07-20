import { ChevronLeft, ChevronRight, ExternalLink, FileText, Loader2, Maximize2, Minimize2, ZoomIn, ZoomOut } from 'lucide-react'
import pdfWorkerUrl from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'
import { Fragment, useEffect, useRef, useState } from 'react'

export function PdfPreview({ url, filename }: { url: string; filename: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const topScrollRef = useRef<HTMLDivElement>(null)
  const fullscreenButtonRef = useRef<HTMLButtonElement>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [pageCount, setPageCount] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [scrollWidth, setScrollWidth] = useState(0)
  const [fullscreen, setFullscreen] = useState(false)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')

  useEffect(() => { setPageNumber(1); setPageCount(0) }, [url])
  useEffect(() => {
    if (!url) return
    let cancelled = false
    let loadingTask: { destroy: () => Promise<void> | void } | undefined
    const render = async () => {
      setStatus('loading')
      try {
        const response = await fetch(url, url.startsWith('blob:') ? undefined : { credentials: 'include' })
        if (!response.ok) throw new Error('Invoice PDF is unavailable')
        const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs')
        if (cancelled) return
        pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl
        const task = pdfjs.getDocument({ data: new Uint8Array(await response.arrayBuffer()) })
        loadingTask = task
        const pdf = await task.promise
        const page = await pdf.getPage(Math.min(Math.max(pageNumber, 1), pdf.numPages))
        const canvas = canvasRef.current
        const context = canvas?.getContext('2d')
        if (!canvas || !context || cancelled) return
        setPageCount(pdf.numPages)
        const viewport = page.getViewport({ scale: 1.25 * zoom })
        canvas.width = Math.ceil(viewport.width)
        canvas.height = Math.ceil(viewport.height)
        await page.render({ canvas, canvasContext: context, viewport }).promise
        if (!cancelled) setStatus('ready')
      } catch {
        if (!cancelled) setStatus('error')
      }
    }
    void render()
    return () => { cancelled = true; void loadingTask?.destroy() }
  }, [url, pageNumber, zoom])
  useEffect(() => {
    const stage = stageRef.current
    if (!stage) return
    const update = () => setScrollWidth(stage.scrollWidth)
    update()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(update)
    observer.observe(stage)
    if (canvasRef.current) observer.observe(canvasRef.current)
    return () => observer.disconnect()
  }, [url, pageNumber, zoom, status, fullscreen])
  useEffect(() => {
    if (!fullscreen) return
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setFullscreen(false)
        window.setTimeout(() => fullscreenButtonRef.current?.focus(), 0)
      }
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [fullscreen])

  const toggleFullscreen = () => {
    setFullscreen((value) => !value)
    if (fullscreen) window.setTimeout(() => fullscreenButtonRef.current?.focus(), 0)
  }

  return <Fragment>
    {fullscreen ? <button className="pdf-fullscreen-backdrop" aria-label="Close fullscreen preview" onClick={toggleFullscreen} /> : null}
    <aside className={`pdf-preview ${url ? '' : 'pdf-preview-empty'} ${fullscreen ? 'is-fullscreen' : ''}`}>
      <div className="pdf-preview-title"><FileText size={17} /><strong>{filename || 'Invoice'}</strong></div>
      {url ? <>
        <div className="pdf-toolbar">
          <div className="pdf-page-controls"><button className="icon-button" aria-label="Previous page" disabled={pageNumber <= 1} onClick={() => setPageNumber((number) => number - 1)}><ChevronLeft size={15} /></button><span>{pageCount ? `Page ${pageNumber} of ${pageCount}` : 'Loading PDF'}</span><button className="icon-button" aria-label="Next page" disabled={!pageCount || pageNumber >= pageCount} onClick={() => setPageNumber((number) => number + 1)}><ChevronRight size={15} /></button></div>
          <div className="pdf-zoom-controls"><button className="icon-button" aria-label="Zoom out" disabled={zoom <= .5} onClick={() => setZoom((number) => Math.max(.5, Number((number - .1).toFixed(1))))}><ZoomOut size={15} /></button><span>{Math.round(zoom * 100)}%</span><button className="icon-button" aria-label="Zoom in" disabled={zoom >= 2} onClick={() => setZoom((number) => Math.min(2, Number((number + .1).toFixed(1))))}><ZoomIn size={15} /></button><button ref={fullscreenButtonRef} className="icon-button" aria-label={fullscreen ? 'Exit fullscreen preview' : 'Open fullscreen preview'} onClick={toggleFullscreen}>{fullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</button><a className="outline-button pdf-open-link" href={url} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open PDF</a></div>
        </div>
        <div ref={topScrollRef} className="pdf-horizontal-scroll" onScroll={(event) => { if (stageRef.current) stageRef.current.scrollLeft = event.currentTarget.scrollLeft }}><div style={{ width: scrollWidth }} /></div>
        <div ref={stageRef} className="pdf-canvas-stage" aria-live="polite" tabIndex={0} onKeyDown={(event) => { if (event.key === '+') setZoom((number) => Math.min(2, Number((number + .1).toFixed(1)))); if (event.key === '-') setZoom((number) => Math.max(.5, Number((number - .1).toFixed(1)))) }} onScroll={(event) => { if (topScrollRef.current) topScrollRef.current.scrollLeft = event.currentTarget.scrollLeft }}>
          <canvas ref={canvasRef} className="pdf-canvas" aria-label={`Page ${pageNumber} of ${filename || 'invoice'}`} />
          {status === 'loading' ? <div className="pdf-loading"><Loader2 className="spin" size={20} /><span>Loading invoice...</span></div> : null}
          {status === 'error' ? <div className="pdf-error"><FileText size={30} /><strong>We could not display this PDF here.</strong><a className="outline-button" href={url} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open PDF</a></div> : null}
        </div>
      </> : <div className="preview-empty"><FileText size={34} /><span>Choose a PDF to view it here.</span></div>}
    </aside>
  </Fragment>
}
