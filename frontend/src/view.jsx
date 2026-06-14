import { createContext, useContext, useEffect, useState } from 'react'
import { api } from './api'

// Global view state: the eval/train flavor (UI-only, localStorage) and the
// global default success metric (persisted server-side). `nonce` bumps when the
// success metric changes so data views refetch.
const ViewContext = createContext(null)

export function ViewProvider({ children }) {
  const [flavor, setFlavorState] = useState(() => localStorage.getItem('cockpit.flavor') || 'eval')
  const [settings, setSettings] = useState(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => { api.getSettings().then(setSettings).catch(() => {}) }, [])

  const setFlavor = (f) => { localStorage.setItem('cockpit.flavor', f); setFlavorState(f) }
  const setSuccessMetric = async (id) => {
    const s = await api.putSettings({ success_metric: id })
    setSettings(s)
    setNonce((n) => n + 1)
  }

  return (
    <ViewContext.Provider value={{ flavor, setFlavor, settings, setSuccessMetric, nonce }}>
      {children}
    </ViewContext.Provider>
  )
}

export const useView = () => useContext(ViewContext)
