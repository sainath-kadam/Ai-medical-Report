import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import ToastProvider from './components/ui/Toast/ToastProvider';
import { queryClient } from './lib/queryClient';
import './index.css';

// QueryClientProvider sits above everything that fetches data -- one cache shared by
// every page for the lifetime of the tab (see lib/queryClient.ts for the freshness
// window/defaults). AuthProvider stays a separate React Context, not a query: it's
// session state driven by its own login/logout/refresh flow, not a page's GET-and-cache.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider>
          <ToastProvider>
            <AuthProvider>
              <App />
            </AuthProvider>
          </ToastProvider>
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
