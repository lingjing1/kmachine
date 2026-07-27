import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { NavLink, useLocation } from 'react-router-dom';
import { FaBookOpen, FaChartBar, FaChevronLeft, FaBookmark } from 'react-icons/fa';
import { GrScorecard } from 'react-icons/gr';
import { MdClass, MdOutlineRateReview } from 'react-icons/md';
import { PiStudentBold } from 'react-icons/pi';
import { LuBlocks } from 'react-icons/lu';
import { useUser } from '../../contexts/UserContext';
import { getEnrolledCourses } from '../../services/studentApi';
import { isAllowedForKappaEval } from '../../services/kappaEvalApi';

interface StudentSidebarProps {
  courseId?: string;
  isSidebarOpen: boolean;
  onToggle: () => void;
}

function StudentSidebar({ courseId, isSidebarOpen, onToggle }: StudentSidebarProps) {
  const { user } = useUser();
  const [isTextVisible, setIsTextVisible] = useState(true);
  const location = useLocation();

  // Use react-query for enrolled courses list
  const { data: coursesData } = useQuery({
    queryKey: ['enrolled-courses', user?.user_id],
    queryFn: () => getEnrolledCourses(),
    enabled: !!user?.user_id,
  });

  const courses = Array.isArray(coursesData) ? coursesData : [];

  useEffect(() => {
    if (isSidebarOpen) {
      const timer = setTimeout(() => setIsTextVisible(true), 100);
      return () => clearTimeout(timer);
    } else {
      setIsTextVisible(false);
    }
  }, [isSidebarOpen]);

  const dropdownItemClass = (isActive: boolean) =>
    `relative flex items-center min-h-[2.5rem] py-2 px-4 no-underline rounded-lg text-sm font-medium transition-all duration-200 ease-smooth
    ${isActive
      ? 'text-blue-700 bg-white font-bold shadow-sm ring-1 ring-blue-50'
      : 'text-neutral-text-tertiary hover:text-blue-700 hover:bg-sky-50'
    }
    ${isSidebarOpen ? 'gap-3 pl-4' : 'justify-center pl-0'}`;

  return (
    <aside
      className={`
        bg-transparent border-r border-gray-200 py-6 h-full flex-shrink-0
        transition-[width] duration-300 ease-smooth overflow-x-hidden
        ${isSidebarOpen ? 'w-72' : 'w-20'} 
      `}
    >
      <div className={`flex flex-col h-full ${isSidebarOpen ? 'px-6' : 'px-2'}`}>

        {/* Header - Sticky with high z-index to stay visible above Footer */}
        <div
          className={`
            sticky top-0 z-50 pt-0 pb-2 mb-4 bg-transparent flex items-center 
            ${isSidebarOpen ? 'justify-between' : 'justify-center'}
          `}
        >
          {isSidebarOpen && (
            <div className={`flex items-center gap-3 overflow-hidden transition-opacity duration-150 ${isTextVisible ? 'opacity-100' : 'opacity-0'}`}>
              <PiStudentBold className="w-8 h-8 text-blue-700 flex-shrink-0" />
              <div className="flex flex-col">
                <span className="text-xs text-neutral-text-secondary whitespace-nowrap">歡迎，</span>
                <span className="text-base font-bold text-neutral-text-main truncate">{user?.full_name} 同學</span>
              </div>
            </div>
          )}

          <button
            onClick={onToggle}
            className="p-2 rounded-lg text-neutral-icon hover:bg-theme-surface-hover hover:text-neutral-icon-hover flex-shrink-0 focus:outline-none transition-colors duration-200"
            title={isSidebarOpen ? "收起選單" : "展開選單"}
          >
            <FaChevronLeft
              className={`w-5 h-5 transition-transform duration-300 ${!isSidebarOpen && 'rotate-180'}`}
            />
          </button>
        </div>

        {/* Sidebar Body - Lower z-index than Footer (z-40) */}
        <div className="relative z-20 flex flex-col flex-1 overflow-hidden">
          {courseId && (
            <NavLink
              to="/student"
              className={({ isActive }) => `
                flex-shrink-0 flex items-center h-12 px-4 rounded-lg font-medium transition-all duration-200 ease-smooth mb-2
                ${isActive ? 'text-blue-800' : 'text-neutral-text-secondary hover:bg-theme-surface-hover hover:text-blue-700'}
                ${isSidebarOpen ? 'gap-3' : 'justify-center'}
              `}
            >
              <LuBlocks className="flex-shrink-0 w-6 h-6 text-blue-700" title="返回課程總覽" />
              {isSidebarOpen && (
                <span className={`flex-grow whitespace-nowrap transition-opacity duration-150 text-base font-bold ${isTextVisible ? 'opacity-100' : 'opacity-0'}`}>
                  返回課程總覽
                </span>
              )}
            </NavLink>
          )}

          <NavLink
            to="/student"
            className={({ isActive }) => `
              flex-shrink-0 flex items-center h-12 px-4 rounded-lg font-medium transition-all duration-200 ease-smooth mb-2
              ${isActive ? 'text-blue-800' : 'text-neutral-text-secondary hover:bg-theme-surface-hover hover:text-blue-700'}
              ${isSidebarOpen ? 'gap-3' : 'justify-center'}
            `}
          >
            <MdClass className="flex-shrink-0 w-6 h-6 text-blue-700" />
            {isSidebarOpen && (
              <span className={`flex-grow whitespace-nowrap transition-opacity duration-150 text-base font-bold ${isTextVisible ? 'opacity-100' : 'opacity-0'}`}>
                我的課程
              </span>
            )}
          </NavLink>

          <nav className="flex-1 overflow-y-auto mt-1 custom-scrollbar pb-24">
            <ul className="list-none p-0 m-0 space-y-2">
              <li>
                <div className={`overflow-hidden transition-all duration-300 ease-in-out ${isSidebarOpen ? 'opacity-100' : 'max-h-0 opacity-0'}`}>
                  <div className="flex ml-0.5 border-l-2 border-gray-100 pl-2 mb-2">
                    <ul className="flex-1 space-y-1">
                      {Array.isArray(courses) && courses.map(course => {
                        const isCourseActive = String(course.id) === String(courseId);
                        const isAtCourseRoot = isCourseActive && location.pathname === `/student/course/${course.id}`;
                        return (
                          <li key={course.id}>
                            <NavLink
                              to={`/student/course/${course.id}`}
                              className={() => dropdownItemClass(isAtCourseRoot)}
                            >
                              <FaBookmark className={`flex-shrink-0 w-3.5 h-3.5 mt-0.5 ${isCourseActive ? 'text-blue-700' : 'text-gray-400 group-hover:text-blue-700'}`} />
                              <span className={`whitespace-normal break-words transition-opacity duration-150 text-sm leading-tight pr-2 ${isCourseActive ? 'font-bold text-blue-800' : 'text-neutral-text-main group-hover:text-blue-700'}`}>
                                {course.name}
                              </span>
                            </NavLink>
                            {isCourseActive && isSidebarOpen && (
                              <div className="ml-8 mt-1 mb-2 space-y-1 border-l border-blue-100 pl-2">
                                <NavLink
                                  to={`/student/course/${course.id}`}
                                  end
                                  className={({ isActive }) =>
                                    `flex items-center h-9 px-2 rounded-md text-sm transition-all duration-200 ${isActive ? 'bg-white text-blue-700 font-bold shadow-sm' : 'text-neutral-text-tertiary hover:bg-sky-50 hover:text-blue-700'
                                    } ${isTextVisible ? 'opacity-100' : 'opacity-0'}`
                                  }
                                >
                                  <FaBookOpen className="mr-2 w-3.5 h-3.5" />
                                  <span className="whitespace-nowrap">課程內容</span>
                                </NavLink>
                                <NavLink
                                  to={`/student/course/${course.id}/dashboard`}
                                  className={({ isActive }) =>
                                    `flex items-center h-9 px-2 rounded-md text-sm transition-all duration-200 ${isActive ? 'bg-white text-blue-700 font-bold shadow-sm' : 'text-neutral-text-tertiary hover:bg-sky-50 hover:text-blue-700'
                                    } ${isTextVisible ? 'opacity-100' : 'opacity-0'}`
                                  }
                                >
                                  <FaChartBar className="mr-2 w-3.5 h-3.5" />
                                  <span className="whitespace-nowrap">學習儀表版</span>
                                </NavLink>
                                <NavLink
                                  to={`/student/course/${course.id}/grades`}
                                  className={({ isActive }) =>
                                    `flex items-center h-9 px-2 rounded-md text-sm transition-all duration-200 ${isActive ? 'bg-white text-blue-700 font-bold shadow-sm' : 'text-neutral-text-tertiary hover:bg-sky-50 hover:text-blue-700'
                                    } ${isTextVisible ? 'opacity-100' : 'opacity-0'}`
                                  }
                                >
                                  <GrScorecard className="mr-2 w-3.5 h-3.5" />
                                  <span className="whitespace-nowrap">成績概覽</span>
                                </NavLink>
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                </div>
              </li>

              {/* Kappa Evaluation Center (白名單僅 user_id 34 / 6 顯示) */}
              {isAllowedForKappaEval(user?.user_id) && (
                <li className="mt-4 pt-4 border-t border-gray-100">
                  <NavLink
                    to="/teacher/kappa-evaluation"
                    className={({ isActive }) => `
                      w-full flex items-center h-12 px-4 rounded-lg font-medium transition-all duration-200 ease-smooth
                      ${isActive ? 'text-blue-800 bg-white font-bold' : 'text-neutral-text-secondary hover:bg-theme-surface-hover hover:text-blue-700'}
                      ${isSidebarOpen ? 'gap-3' : 'justify-center'}
                    `}
                  >
                    <MdOutlineRateReview className={`flex-shrink-0 w-6 h-6 ${location.pathname.includes('/kappa-evaluation') ? 'text-blue-700' : 'text-gray-500'}`} title="Kappa 評估中心" />
                    {isSidebarOpen && (
                      <span className={`flex-grow text-left whitespace-nowrap transition-opacity duration-150 text-base ${location.pathname.includes('/kappa-evaluation') ? 'font-bold' : ''} ${isTextVisible ? 'opacity-100' : 'opacity-0'}`}>
                        Kappa 評估中心
                      </span>
                    )}
                  </NavLink>
                </li>
              )}
            </ul>
          </nav>

        </div>
      </div>
    </aside>
  );
}

export default StudentSidebar;