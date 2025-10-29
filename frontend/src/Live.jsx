import React, { useEffect, useState } from 'react'

export default function Live() {
  const [frames, setFrames] = useState([])

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.hostname || 'localhost'
    const ws = new WebSocket(`${proto}://${host}:8000/ws/frames`)

    ws.addEventListener('message', (ev) => {
      try {
        const payload = JSON.parse(ev.data)
        setFrames((s) => [payload].concat(s).slice(0, 20))
      } catch (e) {
        // ignore
      }
    })

    return () => ws.close()
  }, [])

  return (
    <div className="live">
      {frames.length === 0 ? <div>No frames yet</div> : (
        <table>
          <thead><tr><th>ts</th><th>id</th><th>data</th></tr></thead>
          <tbody>
            {frames.map((f, i) => (
              <tr key={i}><td>{f.timestamp || ''}</td><td>{f.id}</td><td>{JSON.stringify(f.data)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
