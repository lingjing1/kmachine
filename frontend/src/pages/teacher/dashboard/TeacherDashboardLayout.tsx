import { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaChalkboardTeacher, FaChevronRight } from 'react-icons/fa';

interface TeacherDashboardLayoutProps {
  children: ReactNode;
  title: string;
  breadcrumbs?: { label: string; path?: string }[];
}

export default function TeacherDashboardLayout({ children, title, breadcrumbs }: TeacherDashboardLayoutProps) {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gray-50 font-sans text-neutral-text-main">
      {/* Top Navigation Bar */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xl font-bold text-theme-primary cursor-pointer" onClick={() => navigate('/teacher/dashboard')}>
              <FaChalkboardTeacher className="text-2xl" />
              <span>教師儀表板</span>
            </div>
            
            {breadcrumbs && breadcrumbs.length > 0 && (
              <div className="hidden md:flex items-center text-sm text-gray-500 ml-4 border-l border-gray-300 pl-4">
                {breadcrumbs.map((crumb, idx) => (
                  <div key={idx} className="flex items-center">
                    {idx > 0 && <FaChevronRight className="mx-2 text-gray-400 text-xs" />}
                    {crumb.path ? (
                      <span 
                        onClick={() => navigate(crumb.path!)}
                        className="hover:text-theme-primary cursor-pointer transition-colors"
                      >
                        {crumb.label}
                      </span>
                    ) : (
                      <span className="font-medium text-gray-700">{crumb.label}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-4">
            <button className="text-sm text-gray-600 hover:text-theme-primary">
              登出
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
        </div>
        {children}
      </main>
    </div>
  );
}
