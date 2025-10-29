import React, { useState } from 'react'
import { sendFrame } from './api'

export default function SendFrame() {
  const [id, setId] = useState('')
  const [data, setData] = useState('')
  const [resp, setResp] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    const payload = { id, data: data.split(',').map((b) => parseInt(b, 10)) }
    const r = await sendFrame(payload)
    setResp(r)
  }

  return (
    <form onSubmit={submit} className="send-frame">
      <div>
        <label>CAN ID: <input value={id} onChange={(e) => setId(e.target.value)} /></label>
      </div>
      <div>
        <label>Data (comma separated bytes): <input value={data} onChange={(e) => setData(e.target.value)} /></label>
      </div>
      <button type="submit">Send</button>
      {resp && <pre>{JSON.stringify(resp, null, 2)}</pre>}
    </form>
  )
}
