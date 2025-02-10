import { jsx as _jsx } from "react/jsx-runtime";
import ReactDOM from 'react-dom/client';
import App from './App.js';
ReactDOM.createRoot(document.getElementById('root')).render(
// Eliminamos StrictMode para pruebas:
//<React.StrictMode>
_jsx(App, {})
//</React.StrictMode>
);
