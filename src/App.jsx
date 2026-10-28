import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Navbar from './components/Navbar';
import Planned from './pages/Planned';
import PlannedVsActual from './pages/PlannedVsActual';

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen flex-col bg-gray-50 font-sans text-gray-900">
        <Navbar />
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
          <Routes>
            <Route path="/" element={<Navigate to="/planned" replace />} />
            <Route path="/planned" element={<Planned />} />
            <Route path="/actual" element={<PlannedVsActual />} />
            <Route
              path="/planned-vs-actual"
              element={<Navigate to="/actual" replace />}
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
