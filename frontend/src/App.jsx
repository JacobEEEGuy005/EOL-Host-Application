import React, { useEffect, useState } from 'react'
import { listDbcs } from './api'
import Live from './Live'
import SendFrame from './SendFrame'

export default function App() {
  const [dbcs, setDbcs] = useState([])

  useEffect(() => {
    listDbcs().then(setDbcs).catch(() => setDbcs([]))
  }, [])

  return (
    <div className="app">
      <header>
        <h1>EOL Host</h1>
      </header>
      <main>
        <section>
          <h2>Available DBCs</h2>
          <ul>
            {dbcs.map((d) => (
              <li key={d.filename}>{d.original_name || d.filename}</li>
            ))}
          </ul>
        </section>

        <section>
          <h2>Live Frames</h2>
          <Live />
        </section>

        <section>
          <h2>Send Frame</h2>
          <SendFrame />
        </section>
      </main>
    </div>
  )
}
