export function percent(value: number | null | undefined) {
  return value == null ? '-' : `${(value * 100).toFixed((value * 100) % 1 ? 1 : 0)}%`
}

export function duration(seconds: number | null) {
  if (seconds == null) return 'Not recorded'
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

export function cost(value: number | null) {
  return value == null ? 'Not recorded' : `$${value.toFixed(value < 0.1 ? 4 : 2)}`
}

export function delta(value: number | null) {
  if (value == null) return '-'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)} pp`
}

export function shortDate(value: string | null) {
  if (!value) return 'Unknown date'
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(
    new Date(value),
  )
}
