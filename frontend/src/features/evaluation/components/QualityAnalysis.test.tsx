import { render, screen, cleanup } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { EvaluationRun } from '../types'
import { QualitySummary } from './QualityAnalysis'

afterEach(cleanup)

const legacy = {
  passed: true,
  verdict_available: true,
  field_match: 1,
  validation_match: 1,
  documents: 2,
  fields_matched: 16,
  fields_total: 16,
} as EvaluationRun

describe('Quality summary metric scope', () => {
  it('does not present legacy header accuracy as full-invoice accuracy', () => {
    render(<QualitySummary run={legacy} />)
    expect(screen.getByText('Header field match')).toBeInTheDocument()
    expect(
      screen.getByText('Not measured: complete header, line and source labels required'),
    ).toBeInTheDocument()
    expect(screen.getAllByText('N/A')).toHaveLength(3)
  })

  it('shows line errors even when the legacy header gate passes', () => {
    render(
      <QualitySummary
        run={{
          ...legacy,
          report_version: '2.0',
          full_invoice_exact_match: 0,
          full_invoice_documents_total: 2,
          full_invoice_documents_matched: 0,
          line_field_match: 0.875,
          missing_lines: 1,
          extra_lines: 2,
          processing_completion: 1,
          validation_completion: 1,
          evaluation_input: 'original_provider_extraction',
        }}
      />,
    )
    expect(screen.getByText('0%')).toBeInTheDocument()
    expect(screen.getByText('0/2 fully labeled invoices (2 total)')).toBeInTheDocument()
    expect(screen.getByText('1 missing / 2 extra lines')).toBeInTheDocument()
    expect(screen.getByText('Original extraction, before reviewer corrections')).toBeInTheDocument()
  })
})
