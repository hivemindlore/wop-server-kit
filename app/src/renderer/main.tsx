import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import type { WopApi } from '@shared/api'
import { App } from './views/App'
import './styles.css'

declare global {
  interface Window {
    wop: WopApi
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App api={window.wop} />
  </StrictMode>
)
