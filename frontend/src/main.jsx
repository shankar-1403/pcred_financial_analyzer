import { createRoot } from 'react-dom/client'
import { StackedSnackbarProvider } from './components/SnackbarProvider.jsx'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
    <StackedSnackbarProvider>
        <App />
    </StackedSnackbarProvider>
)