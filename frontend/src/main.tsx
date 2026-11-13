import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { AuthGate } from './components/AuthGate';
import { accountAuthEnabled } from './services/auth';
import './styles/index.css';
import './styles/workspace.css';
import './pages/Overview.css';
import './pages/Report.css';
import './styles/product-ui.css';
import './styles/workbench-light.css';
import './styles/workspace-nav.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {accountAuthEnabled ? <AuthGate /> : <App />}
  </StrictMode>,
);
