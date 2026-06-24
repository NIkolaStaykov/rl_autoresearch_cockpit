import { createContext, useContext, useState } from 'react'

// Global view state: the eval/train flavor (UI-only, persisted to localStorage).
const ViewContext = createContext(null)

export function ViewProvider({ children }) {
  const [flavor, setFlavorState] = useState(() => localStorage.getItem('cockpit.flavor') || 'eval')

  const setFlavor = (f) => { localStorage.setItem('cockpit.flavor', f); setFlavorState(f) }

  return (
    <ViewContext.Provider value={{ flavor, setFlavor }}>
      {children}
    </ViewContext.Provider>
  )
}

export const useView = () => useContext(ViewContext)
