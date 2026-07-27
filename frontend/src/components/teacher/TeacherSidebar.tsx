import { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { NavLink, useNavigate } from 'react-router-dom';
import { FaChartBar, FaBookOpen, FaChevronLeft, FaBookmark, FaTrash, FaUndo, FaUsers } from 'react-icons/fa';
import { FaChalkboardUser } from "react-icons/fa6";
import { GrScorecard, GrTest } from "react-icons/gr";
import { MdOutlineBookmarkAdd, MdOutlineDeleteSweep, MdAdminPanelSettings, MdClass, MdScience, MdOutlineRateReview } from "react-icons/md";
import { LuBlocks } from "react-icons/lu";

import { useUser } from '../../contexts/UserContext';
import { isAllowedForKappaEval } from '../../services/kappaEvalApi';
import API_BASE_URL from '../../config/api';
import Toast from '../common/Toast';
import ConfirmDialog from '../common/ConfirmDialog';
import CreateCourseModal from './CreateCourseModal';
import Tooltip from '../common/Tooltip';

interface Course {
  id: number;
  name: string;
  semester: string;
}

interface TeacherSidebarProps {
  courseId?: string;
  isSidebarOpen: boolean;
  onToggle: () => void;
}

function TeacherSidebar({ courseId, isSidebarOpen, onToggle }: TeacherSidebarProps) {
  const { user } = useUser();
  const navigate = useNavigate();
  const [isTextVisible, setIsTextVisible] = useState(true);
  const [isCoursesOpen] = useState(true);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isTrashOpen, setIsTrashOpen] = useState(false);
  const queryClient = useQueryClient();

  // Toast state
  const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'error' | 'info' }>(
    { show: false, message: '', type: 'success' }
  );

  // Confirm dialog state
  const [confirmDialog, setConfirmDialog] = useState<{ show: boolean; courseId: number | null }>(
    { show: false, courseId: null }
  );

  // Fetch courses using React Query
  const { data: courses = [], isLoading } = useQuery({
    queryKey: ['courses', 'teacher', user?.user_id],
    queryFn: async () => {
      if (!user?.user_id) return [];
      const endpoint = user.role === 'admin'
        ? `${API_BASE_URL}/api/courses`
        : `${API_BASE_URL}/api/teachers/${user.user_id}/courses`;

      const response = await fetch(endpoint);
      if (!response.ok) throw new Error('Failed to fetch courses');
      const data = await response.json();
      const mappedCourses = data.map((c: any) => ({
        id: c.id,
        name: c.name,
        semester: c.semester
      }));

      // Apply saved order
      const savedOrder = localStorage.getItem(`teacher_${user.user_id}_course_order`);
      if (savedOrder) {
        try {
          const orderArray: number[] = JSON.parse(savedOrder);
          const orderedCourses = orderArray
            .map(id => mappedCourses.find((c: any) => c.id === id))
            .filter(Boolean);
          const newCourses = mappedCourses.filter(
            (c: any) => !orderArray.includes(c.id)
          );
          return [...orderedCourses, ...newCourses];
        } catch (e) {
          return mappedCourses;
        }
      }
      return mappedCourses;
    },
    enabled: !!user?.user_id,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const { data: deletedCourses = [] } = useQuery({
    queryKey: ['courses', 'teacher', user?.user_id, 'deleted'],
    queryFn: async () => {
      if (!user?.user_id) return [];
      const response = await fetch(`${API_BASE_URL}/api/teachers/${user.user_id}/deleted-courses`);
      if (!response.ok) throw new Error('Failed to fetch deleted courses');
      const data = await response.json();
      return data.map((c: any) => ({
        id: c.id,
        name: c.name,
        semester: c.semester
      }));
    },
    enabled: !!user?.user_id,
    staleTime: 5 * 60 * 1000,
  });

  const setCourses = (newCourses: Course[]) => {
    queryClient.setQueryData(['courses', 'teacher', user?.user_id], newCourses);
  };

  const saveCourseOrder = (orderedCourses: any[]) => {
    if (!user?.user_id) return;
    const orderArray = orderedCourses.map(c => c.id);
    localStorage.setItem(`teacher_${user.user_id}_course_order`, JSON.stringify(orderArray));
  };

  // Drag and drop handlers
  const [draggedCourseId, setDraggedCourseId] = useState<number | null>(null);
  const [dragOverCourseId, setDragOverCourseId] = useState<number | null>(null);

  const handleDragStart = (e: React.DragEvent, courseId: number) => {
    setDraggedCourseId(courseId);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent, courseId: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverCourseId(courseId);
  };

  const handleDragLeave = () => {
    setDragOverCourseId(null);
  };

  const handleDrop = (e: React.DragEvent, targetCourseId: number) => {
    e.preventDefault();

    if (!draggedCourseId || draggedCourseId === targetCourseId) {
      setDraggedCourseId(null);
      setDragOverCourseId(null);
      return;
    }

    const draggedIndex = courses.findIndex((c: Course) => c.id === draggedCourseId);
    const targetIndex = courses.findIndex((c: Course) => c.id === targetCourseId);

    if (draggedIndex === -1 || targetIndex === -1) return;

    const newCourses = [...courses];
    const [removed] = newCourses.splice(draggedIndex, 1);
    newCourses.splice(targetIndex, 0, removed);

    setCourses(newCourses);
    saveCourseOrder(newCourses);
    setDraggedCourseId(null);
    setDragOverCourseId(null);
  };

  const handleDragEnd = () => {
    setDraggedCourseId(null);
    setDragOverCourseId(null);
  };



  const handleCourseCreated = (courseId: number) => {
    queryClient.invalidateQueries({ queryKey: ['courses', 'teacher', user?.user_id] });
    setToast({ show: true, message: '課程建立成功！', type: 'success' });
    setTimeout(() => {
      navigate(`/teacher/courses/${courseId}`);
    }, 500);
  };

  const handleDeleteCourse = async (deleteCourseId: number) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/courses/${deleteCourseId}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        setToast({ show: true, message: '課程已刪除', type: 'success' });
        queryClient.invalidateQueries({ queryKey: ['courses', 'teacher', user?.user_id] });
        queryClient.invalidateQueries({ queryKey: ['courses', 'teacher', user?.user_id, 'deleted'] });

        if (String(deleteCourseId) === courseId) {
          const remainingCourses = courses.filter((c: Course) => c.id !== deleteCourseId);
          if (remainingCourses.length > 0) {
            navigate(`/teacher/courses/${remainingCourses[0].id}`);
          } else {
            navigate('/teacher');
          }
        }
      } else {
        setToast({ show: true, message: '刪除課程失敗', type: 'error' });
      }
    } catch (error) {
      console.error('Failed to delete course:', error);
      setToast({ show: true, message: '刪除課程失敗', type: 'error' });
    }
    setConfirmDialog({ show: false, courseId: null });
  };

  const handleRestoreCourse = async (restoreCourseId: number) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/courses/${restoreCourseId}/restore`, {
        method: 'POST'
      });

      if (response.ok) {
        setToast({ show: true, message: '課程已恢復', type: 'success' });
        queryClient.invalidateQueries({ queryKey: ['courses', 'teacher', user?.user_id] });
        queryClient.invalidateQueries({ queryKey: ['courses', 'teacher', user?.user_id, 'deleted'] });
      } else {
        setToast({ show: true, message: '恢復課程失敗', type: 'error' });
      }
    } catch (error) {
      console.error('Failed to restore course:', error);
      setToast({ show: true, message: '恢復課程失敗', type: 'error' });
    }
  };

  useEffect(() => {
    if (isSidebarOpen) {
      const timer = setTimeout(() => setIsTextVisible(true), 100);
      return () => clearTimeout(timer);
    } else {
      setIsTextVisible(false);
      // setIsCoursesOpen(false); // Keep it open or logic as desired, user requested default open
    }
  }, [isSidebarOpen]);

  // Match StudentSidebar navLinkClass exactly
  // Match StudentSidebar navLinkClass exactly

  // Helper for dropdown items
  const dropdownItemClass = (isActive: boolean) =>
    `relative flex items-center min-h-[2.5rem] py-2 px-4 pl-8 ${isSidebarOpen ? 'pr-12' : ''} no-underline rounded-lg text-sm font-medium transition-all duration-200 ease-smooth
    ${isActive
      ? 'text-blue-700 bg-white font-bold'
      : 'text-neutral-text-tertiary hover:text-blue-700 hover:bg-sky-50'
    }
    ${isSidebarOpen ? 'gap-3' : 'justify-center'}`;

  return (
    <aside
      className={`
        bg-transparent border-r border-gray-200 py-6 h-full flex-shrink-0
        transition-[width] duration-300 ease-smooth
        ${isSidebarOpen ? 'w-72' : 'w-20'} 
      `}
    >
      <div className={`flex flex-col h-full ${isSidebarOpen ? 'px-6' : 'px-2'}`}>
        {/* Header with User Info and Toggle - Sticky and high z-index to stay above Footer */}
        <div
          className={`
            sticky top-0 z-50 pt-0 pb-2 mb-4 bg-transparent flex items-center 
            ${isSidebarOpen ? 'justify-between' : 'justify-center'}
          `}
        >
          {isSidebarOpen && (
            <div className={`flex items-center gap-3 overflow-hidden transition-opacity duration-150 ${isTextVisible ? 'opacity-100' : 'opacity-0'}`}>
              <FaChalkboardUser className="w-8 h-8 text-blue-700 flex-shrink-0" />
              <div className="flex flex-col">
                <span className="text-xs text-neutral-text-secondary whitespace-nowrap">歡迎，</span>
                <span className="text-base font-bold text-neutral-text-main truncate">
                  {user?.full_name} {user?.role === 'admin' ? '' : (user?.role === 'teacher' ? '教師' : '助教')}
                </span>
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
          {(user?.role !== 'teacher' && user?.role !== 'admin') && (
            <NavLink
              to="/student"
              className={({ isActive }) => `
                flex-shrink-0 flex items-center h-12 px-4 rounded-lg font-medium transition-all duration-200 ease-smooth mb-2
                ${isActive ? 'text-blue-800' : 'text-neutral-text-secondary hover:bg-theme-surface-hover hover:text-blue-700'}
                ${isSidebarOpen ? 'gap-3' : 'justify-center'}
              `}
            >
              <LuBlocks className="flex-shrink-0 w-6 h-6 text-blue-700" title="回到課程總覽" />
              {isSidebarOpen && (
                <span className={`flex-grow whitespace-nowrap transition-opacity duration-150 text-base font-bold ${isTextVisible ? 'opacity-100' : 'opacity-0'}`}>
                  回到課程總覽
                </span>
              )}
            </NavLink>
          )}

          {user?.role === 'admin' && (
            <NavLink
              to="/admin"
              className={({ isActive }) => `
                flex-shrink-0 flex items-center h-12 px-4 rounded-lg font-medium transition-all duration-200 ease-smooth mb-2
                ${isActive ? 'text-blue-800' : 'text-neutral-text-secondary hover:bg-theme-surface-hover hover:text-blue-700'}
                ${isSidebarOpen ? 'gap-3' : 'justify-center'}
              `}
            >
              <MdAdminPanelSettings className="flex-shrink-0 w-6 h-6 text-blue-700" title="管理中心" />
              {isSidebarOpen && (
                <span className={`flex-grow whitespace-nowrap transition-opacity duration-150 text-base font-bold ${isTextVisible ? 'opacity-100' : 'opacity-0'}`}>
                  回到管理中心
                </span>
              )}
            </NavLink>
          )}

          {/* Fixed Header: My Courses Title */}
          <div className="flex items-center gap-1 mb-2">
            <NavLink
              to="/teacher"
              className={({ isActive }) => `
                flex-grow flex items-center h-12 px-4 rounded-lg font-medium transition-all duration-200 ease-smooth
                ${isActive ? 'text-blue-800' : 'text-neutral-text-secondary hover:bg-theme-surface-hover hover:text-blue-700'}
                ${isSidebarOpen ? 'gap-3' : 'justify-center'}
              `}
            >
              <MdClass className="flex-shrink-0 w-6 h-6 text-blue-700" />
              {isSidebarOpen && (
                <span className={`flex-grow whitespace-nowrap transition-opacity duration-150 text-base font-bold ${isTextVisible ? 'opacity-100' : 'opacity-0'}`}>
                  {user?.role === 'admin' ? '所有課程' : (user?.role === 'teacher' ? '我的課程' : '助教課程')}
                </span>
              )}
            </NavLink>
            {isSidebarOpen && (user?.role === 'teacher' || user?.role === 'admin') && (
              <Tooltip content="新增課程" position="bottom" className="flex-shrink-0">
                <button
                  onClick={() => setIsCreateModalOpen(true)}
                  className="p-2 hover:bg-theme-surface-hover rounded-lg text-neutral-icon hover:text-blue-600 transition-colors"
                >
                  <MdOutlineBookmarkAdd size={20} />
                </button>
              </Tooltip>
            )}
          </div>

          {/* Navigation - Scrollable part */}
          <nav className="flex-1 overflow-y-auto mt-1 custom-scrollbar pb-24">
            <ul className="list-none p-0 m-0 space-y-2">
              <li>
                {/* Dropdown Content with Vertical Line */}
                <div className={`overflow-hidden transition-all duration-300 ease-in-out ${isCoursesOpen && isSidebarOpen ? 'opacity-100' : 'max-h-0 opacity-0'}`}>
                  <div className="flex ml-0.5 border-l-2 border-gray-100 pl-2 mb-2">
                    <ul className="flex-1 space-y-1">
                      {isLoading ? (
                        <li className="px-3 py-2 text-sm text-neutral-text-tertiary text-center">
                          載入中...
                        </li>
                      ) : courses.length === 0 ? (
                        <li className="px-3 py-2 text-sm text-neutral-text-tertiary text-center">
                          尚未開設課程
                        </li>
                      ) : (
                        courses.map((course: Course) => {
                          const isCourseActive = courseId === String(course.id);
                          const isDragging = draggedCourseId === course.id;
                          const isDragOver = dragOverCourseId === course.id;

                          // Check if we are precisely on the course root page
                          const isAtCourseRoot = isCourseActive && location.pathname === `/teacher/courses/${course.id}`;

                          return (
                            <li
                              key={course.id}
                              className={`relative group ${isDragging ? 'opacity-40' : ''} ${isDragOver ? 'border-t-2 border-theme-primary' : ''}`}
                              draggable
                              onDragStart={(e) => handleDragStart(e, course.id)}
                              onDragOver={(e) => handleDragOver(e, course.id)}
                              onDragLeave={handleDragLeave}
                              onDrop={(e) => handleDrop(e, course.id)}
                              onDragEnd={handleDragEnd}
                            >
                              <NavLink
                                to={`/teacher/courses/${course.id}`}
                                className={() => dropdownItemClass(isAtCourseRoot)}
                              >
                                <FaBookmark className={`flex-shrink-0 w-3.5 h-3.5 mt-0.5 ${isCourseActive ? 'text-blue-700' : 'text-gray-400 group-hover:text-blue-700'}`} />
                                <span className={`whitespace-normal break-all text-sm leading-tight pr-2 ${isCourseActive ? 'font-bold text-blue-800' : 'text-neutral-text-main group-hover:text-blue-700'}`}>{course.name}</span>

                                {isSidebarOpen && (
                                  <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
                                    <Tooltip content="移至回收桶" position="right">
                                      <button
                                        onClick={(e) => {
                                          e.preventDefault();
                                          setConfirmDialog({ show: true, courseId: course.id });
                                        }}
                                        className="p-1.5 text-neutral-icon hover:text-destructive rounded"
                                      >
                                        <FaTrash size={12} />
                                      </button>
                                    </Tooltip>
                                  </div>
                                )}
                              </NavLink>

                              {/* Dynamic Sub-menu for active course */}
                              {isCourseActive && (
                                <div className="ml-8 mt-1 mb-2 space-y-1 border-l border-blue-100 pl-2">
                                  <NavLink
                                    to={`/teacher/courses/${course.id}`}
                                    end
                                    className={({ isActive }) =>
                                      `flex items-center h-9 px-2 rounded-md text-sm transition-all duration-200 ${isActive ? 'bg-white text-blue-700 font-bold' : 'text-neutral-text-tertiary hover:bg-sky-50 hover:text-blue-700'
                                      }`
                                    }
                                  >
                                    <FaBookOpen className="mr-2 w-3.5 h-3.5" />
                                    課程內容
                                  </NavLink>
                                  <NavLink
                                    to={`/teacher/courses/${course.id}/members`}
                                    className={({ isActive }) =>
                                      `flex items-center h-9 px-2 rounded-md text-sm transition-all duration-200 ${isActive ? 'bg-white text-blue-700 font-bold' : 'text-neutral-text-tertiary hover:bg-sky-50 hover:text-blue-700'
                                      }`
                                    }
                                  >
                                    <FaUsers className="mr-2 w-3.5 h-3.5" />
                                    成員管理
                                  </NavLink>
                                  <NavLink
                                    to={`/teacher/courses/${course.id}/dashboard`}
                                    className={({ isActive }) =>
                                      `flex items-center h-9 px-2 rounded-md text-sm transition-all duration-200 ${isActive ? 'bg-white text-blue-700 font-bold' : 'text-neutral-text-tertiary hover:bg-sky-50 hover:text-blue-700'
                                      }`
                                    }
                                  >
                                    <FaChartBar className="mr-2 w-3.5 h-3.5" />
                                    學生學習儀表板
                                  </NavLink>
                                  <NavLink
                                    to={`/teacher/courses/${course.id}/grades`}
                                    className={({ isActive }) =>
                                      `flex items-center h-9 px-2 rounded-md text-sm transition-all duration-200 ${isActive ? 'bg-white text-blue-700 font-bold' : 'text-neutral-text-tertiary hover:bg-sky-50 hover:text-blue-700'
                                      }`
                                    }
                                  >
                                    <GrScorecard className="mr-2 w-3.5 h-3.5" />
                                    成績總覽
                                  </NavLink>
                                </div>
                              )}
                            </li>
                          );
                        })
                      )}
                    </ul>
                  </div>
                </div>
              </li>

              {/* Trash / Deleted Courses Section - Only visible when expanded */}
              {deletedCourses.length > 0 && isSidebarOpen && (
                <li className="mt-4 pt-4 border-t border-gray-100">
                  <button
                    onClick={() => setIsTrashOpen(!isTrashOpen)}
                    className={`w-full flex items-center h-12 px-4 rounded-lg font-medium transition-all duration-200 ease-smooth text-neutral-text-secondary hover:bg-theme-surface-hover ${isSidebarOpen ? 'gap-3' : 'justify-center'}`}
                  >
                    <MdOutlineDeleteSweep className="flex-shrink-0 w-6 h-6 text-gray-500" />
                    <span className={`flex-grow text-left whitespace-nowrap transition-opacity duration-150 text-base font-bold text-neutral-text-main ${isTextVisible ? 'opacity-100' : 'opacity-0'} ${!isSidebarOpen && 'hidden'}`}>
                      已刪除的課程 ({deletedCourses.length})
                    </span>
                  </button>

                  {isSidebarOpen && isTrashOpen && (
                    <div className="ml-0.5 border-l-2 border-dashed border-gray-200 pl-2 mt-1 mb-2">
                      <ul className="space-y-1">
                        {deletedCourses.map((course: Course) => (
                          <li key={course.id} className="relative flex items-center group h-auto min-h-[2.5rem] py-2 px-4 pl-8 pr-12 rounded-md hover:bg-gray-50 transition-colors">
                            <span className="text-sm text-neutral-text-main break-all leading-tight mr-2" title={course.name}>
                              {course.name}
                            </span>
                            <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
                              <Tooltip content="復原課程" position="right">
                                <button
                                  onClick={() => handleRestoreCourse(course.id)}
                                  className="p-1.5 text-blue-600 hover:bg-blue-50 rounded transition-colors"
                                >
                                  <FaUndo size={12} />
                                </button>
                              </Tooltip>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </li>
              )}

              {/* Experiment Evaluation Route */}
              <li className="mt-4 pt-4 border-t border-gray-100">
                <NavLink
                  to="/teacher/experiment/evaluations"
                  className={({ isActive }) => `
                    w-full flex items-center h-12 px-4 rounded-lg font-medium transition-all duration-200 ease-smooth
                    ${isActive ? 'text-blue-800 bg-white font-bold' : 'text-neutral-text-secondary hover:bg-theme-surface-hover hover:text-blue-700'}
                    ${isSidebarOpen ? 'gap-3' : 'justify-center'}
                  `}
                >
                  <MdScience className={`flex-shrink-0 w-6 h-6 ${location.pathname.includes('/experiment/evaluations') ? 'text-blue-700' : 'text-gray-500'}`} title="實驗評估" />
                  {isSidebarOpen && (
                    <span className={`flex-grow text-left whitespace-nowrap transition-opacity duration-150 text-base ${location.pathname.includes('/experiment/evaluations') ? 'font-bold' : ''} ${isTextVisible ? 'opacity-100' : 'opacity-0'}`}>
                      專家評估(實驗)
                    </span>
                  )}
                </NavLink>
              </li>

              {/* Kappa Evaluation Center (白名單僅 user_id 34 / 6 顯示) */}
              {isAllowedForKappaEval(user?.user_id) && (
                <li>
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

          <CreateCourseModal
            isOpen={isCreateModalOpen}
            onClose={() => setIsCreateModalOpen(false)}
            onSuccess={handleCourseCreated}
          />


          <ConfirmDialog
            isOpen={confirmDialog.show}
            title="刪除課程"
            message="確定要將此課程移至回收桶嗎？您稍後仍可以在「已刪除的課程」區塊中將其復原。"
            confirmText="移至回收桶"
            cancelText="取消"
            variant="danger"
            onConfirm={() => confirmDialog.courseId && handleDeleteCourse(confirmDialog.courseId)}
            onCancel={() => setConfirmDialog({ show: false, courseId: null })}
          />

          {
            toast.show && (
              <Toast
                message={toast.message}
                type={toast.type}
                onClose={() => setToast({ ...toast, show: false })}
              />
            )
          }
        </div>
      </div>
    </aside >
  );
}

export default TeacherSidebar;