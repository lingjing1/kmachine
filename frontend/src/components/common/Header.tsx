import { useNavigate, useLocation, Link } from 'react-router-dom';
import { IoIosLogOut } from 'react-icons/io';
import { MdOutlineFeedback } from 'react-icons/md';
import Breadcrumb from './Breadcrumb';
import { useUser } from '../../contexts/UserContext';

interface HeaderProps {
  paths: Array<{ name: string; path: string }> | null;
  actions?: React.ReactNode;
}

function Header({ paths, actions }: HeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useUser();

  const handleLogout = () => {
    navigate('/');
  };



  return (
    <header className="bg-transparent pl-8 pr-8 py-2 flex items-center justify-between gap-4 flex-shrink-0 sticky top-0 z-40">
      {/* Logo - No card background */}
      <div className="text-3xl font-bold gradient-text px-2 pt-2 mr-4">
        CooK.ai
      </div>

      {/* Breadcrumb Card */}
      {paths && paths.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm px-8 py-3 flex-1">
          <Breadcrumb paths={paths} />
        </div>
      )}

      {/* Utility Actions Group */}
      <div className="flex items-center gap-3">
        {/* Custom Actions (e.g., Switch View, Cancel) */}
        {actions && actions}

        {/* Feedback Link for non-admin users */}
        {user?.role !== 'admin' && !location.pathname.endsWith('/feedback') && (
          <Link
            to={location.pathname.startsWith('/teacher') ? '/teacher/feedback' : '/student/feedback'}
            className="
              flex items-center gap-2 px-3 py-2 text-neutral-text-secondary font-medium
              transition-all duration-200 hover:text-blue-600 group
            "
            title="意見回饋"
          >
            <div className="w-10 h-10 rounded-xl bg-white border border-gray-200 shadow-sm flex items-center justify-center transition-all duration-200 group-hover:bg-blue-50 group-hover:border-blue-200">
              <MdOutlineFeedback className="w-5 h-5 flex-shrink-0 group-hover:scale-110 transition-transform" />
            </div>
            <span className="max-lg:hidden whitespace-nowrap">意見回饋</span>
          </Link>
        )}

        {/* Logout */}
        <button
          className="
            flex items-center gap-2 text-neutral-text-secondary font-medium
            transition-all duration-200 hover:text-red-600 group
          "
          onClick={handleLogout}
        >
          <div className="w-10 h-10 rounded-xl bg-white border border-gray-200 shadow-sm flex items-center justify-center transition-all duration-200 group-hover:bg-red-50 group-hover:border-red-200">
            <IoIosLogOut className="w-5 h-5 flex-shrink-0 group-hover:scale-110 transition-transform" />
          </div>
          <span className="max-lg:hidden whitespace-nowrap">登出</span>
        </button>
      </div>
    </header>
  );
}

export default Header;