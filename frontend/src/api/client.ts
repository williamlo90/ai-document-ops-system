export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(path, { ...init, credentials: 'same-origin', headers })
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    throw new Error(`Unexpected response from ${path}. Check the API proxy configuration.`)
  }
  const payload = await response.json() as { detail?: string | { message?: string } }
  if (!response.ok) {
    const message = typeof payload.detail === 'string' ? payload.detail : payload.detail?.message
    throw new Error(message ?? `Request failed with ${response.status}`)
  }
  return payload as T
}

export function upload<T>(path: string, body: FormData, onProgress?: (value: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('POST', path)
    request.withCredentials = true
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    request.onerror = () => reject(new Error('Upload failed because the server could not be reached.'))
    request.onload = () => {
      const payload = safeJson(request.responseText)
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(String(payload.detail ?? `Request failed with ${request.status}`)))
        return
      }
      resolve(payload as T)
    }
    request.send(body)
  })
}

function safeJson(value: string): Record<string, unknown> {
  try {
    return JSON.parse(value) as Record<string, unknown>
  } catch {
    return {}
  }
}
