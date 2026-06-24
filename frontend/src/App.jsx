import { useEffect, useState } from 'react'
import Board from './components/Board'
import QueueDetail from './components/QueueDetail'
import RunDetail from './components/RunDetail'
import { navigate } from './components/Common'
import { ViewProvider, useView } from './view'

// Tiny hash router: #/  #/q/<id>  #/r/<exp>
function parseHash() {
  const h = window.location.hash.replace(/^#\/?/, '')
  if (h.startsWith('q/')) return { view: 'queue', id: decodeURIComponent(h.slice(2)) }
  if (h.startsWith('r/')) return { view: 'run', exp: decodeURIComponent(h.slice(2)) }
  return { view: 'board' }
}

export default function App() {
  return (
    <ViewProvider>
      <AppInner />
    </ViewProvider>
  )
}

function AppInner() {
  const [route, setRoute] = useState(parseHash())

  useEffect(() => {
    const onHash = () => setRoute(parseHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand" style={{ cursor: 'pointer' }} onClick={() => navigate('#/')}>
          <h1>cockpit<span className="dot">.</span></h1>
          <span className="sub">experiment monitor</span>
        </div>
        <div className="spacer" />
        <ViewControls view={route.view} />
        <Crumbs route={route} />
      </div>

      {route.view === 'board' && <Board />}
      {route.view === 'queue' && <QueueDetail id={route.id} />}
      {route.view === 'run' && <RunDetail exp={route.exp} />}
    </div>
  )
}

function ViewControls({ view }) {
  const { flavor, setFlavor } = useView()
  if (view === 'board') return null
  return (
    <div className="viewctl">
      <div className="seg-toggle" role="group" aria-label="train/eval">
        <button className={flavor === 'eval' ? 'on' : ''} onClick={() => setFlavor('eval')}>eval</button>
        <button className={flavor === 'train' ? 'on' : ''} onClick={() => setFlavor('train')}>train</button>
      </div>
    </div>
  )
}

function Crumbs({ route }) {
  if (route.view === 'board') return <span className="meta">all experiments</span>
  return (
    <div className="crumbs">
      <a onClick={() => navigate('#/')}>experiments</a>
      <span className="sep">/</span>
      {route.view === 'queue' && <span>{route.id}</span>}
      {route.view === 'run' && <span>run</span>}
    </div>
  )
}
