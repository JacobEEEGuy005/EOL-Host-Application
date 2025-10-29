export async function listDbcs() {
  const res = await fetch('/api/dbc/list')
  if (!res.ok) return []
  const data = await res.json()
  return data.dbcs || []
}

export async function uploadDbc(file) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch('/api/dbc/upload', { method: 'POST', body: fd })
  return res.ok
}

export async function decodeFrame(payload) {
  const res = await fetch('/api/dbc/decode-frame', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return res.json()
}

export async function sendFrame(payload) {
  // Normalize payload: backend expects { can_id: int, data: hexstring }
  let bodyObj = null
  if (payload == null) throw new Error('payload required')
  // support either { can_id, data } or { id, data } where data can be hex string or array of bytes
  const canId = payload.can_id ?? payload.id ?? payload.canId ?? payload.can
  let data = payload.data ?? payload.bytes ?? payload.payload
  if (canId == null) throw new Error('can id missing')
  if (Array.isArray(data)) {
    // convert array of numbers to hex string
    data = data.map((b) => (b & 0xff).toString(16).padStart(2, '0')).join('')
  } else if (typeof data === 'string') {
    // remove optional commas/spaces if user passed comma-separated bytes
    data = data.replace(/[^0-9a-fA-F]/g, '')
  } else {
    // otherwise try to stringify
    data = String(data)
  }
  bodyObj = { can_id: Number(canId), data }
  const res = await fetch('/api/send-frame', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(bodyObj)
  })
  return res.json()
}
