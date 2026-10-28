import { useLocation } from 'react-router-dom';

export default function Navbar() {
  const location = useLocation();

  // Determine current active page name based on route
  let currentPageName = '';
  if (location.pathname.includes('actual')) {
    currentPageName = 'Planned vs Actual';
  } else if (location.pathname.includes('planned') || location.pathname === '/') {
    currentPageName = 'Planned';
  }

  return (
    <header className="sticky top-0 z-50 border-b border-gray-200 bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Left: Project Name */}
          <div className="flex items-center">
            <span className="text-lg font-bold tracking-tight text-gray-900 sm:text-xl">
              Service Project ROI
            </span>
          </div>

          {/* Right: Static Text Only (No border, No link) */}
          {currentPageName && (
            <div className="flex items-center">
              <span className="cursor-default select-none text-sm font-semibold text-[#0c72af]">
                {currentPageName}
              </span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
