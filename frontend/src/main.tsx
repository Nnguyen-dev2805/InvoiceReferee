import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './settlement/App';
import './styles.css';

const container = document.getElementById('root');
if (!container) throw new Error('Không tìm thấy phần tử #root.');

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
