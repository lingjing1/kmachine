// frontend/src/pages/student/StudentOverview.tsx
import { useState, useEffect } from 'react';
import { useNavigate, useOutletContext, Link } from 'react-router-dom';
import { FaBookOpen, FaBell, FaChevronRight, FaUserGraduate, FaPlus, FaChalkboardTeacher, FaChevronDown, FaFilePdf, FaFileWord, FaFilePowerpoint, FaFileAlt, FaUserShield, FaThumbtack } from 'react-icons/fa';
import Spinner from '../../components/common/Spinner';
import Modal from '../../components/common/Modal';
import Toast from '../../components/common/Toast';

// Define a type for the course object

import { getAllStudentAnnouncements, getEnrolledCourses, joinCourse } from '../../services/studentApi';
import { useQueryClient, useQuery } from '@tanstack/react-query';
import { formatDateTime } from '../../utils/dateUtils';
import API_BASE_URL from '../../config/api';
import { useUser } from '../../contexts/UserContext';

// ... (keep MOCK_ANNOUNCEMENTS removed or commented out if you prefer, but we are removing usage)

function Overview() {
  const queryClient = useQueryClient();
  const { user, refreshAuthenticatedUser } = useUser();
  const navigate = useNavigate();
  const { setHeaderActions } = useOutletContext<any>() || {};

  // Join Course State
  const [showJoinModal, setShowJoinModal] = useState(false);
  const [joinCode, setJoinCode] = useState('');
  const [isJoining, setIsJoining] = useState(false);
  const [expandedAnnouncements, setExpandedAnnouncements] = useState<number[]>([]);
  const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'error' | 'info' }>(
    { show: false, message: '', type: 'success' }
  );

  // Queries using TanStack Query for deduplication
  const {
    data: courses = [],
    isLoading: isCoursesLoading,
    error: coursesError
  } = useQuery({
    queryKey: ['enrolled-courses'],
    queryFn: getEnrolledCourses,
    enabled: !!user,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const {
    data: announcements = [],
    isLoading: isAnnouncementsLoading,
    error: announcementsError
  } = useQuery({
    queryKey: ['all-announcements'],
    queryFn: getAllStudentAnnouncements,
    enabled: !!user,
    staleTime: 5 * 60 * 1000,
  });

  const isLoading = isCoursesLoading || isAnnouncementsLoading;
  const error = coursesError || announcementsError ? '無法取得資料，請稍後再試' : null;

  // Add Teacher View Button if user is teacher
  useEffect(() => {
    if (user?.role === 'teacher' && setHeaderActions) {
      setHeaderActions(
        <button
          onClick={() => navigate('/teacher')}
          className="
            flex items-center gap-2 text-neutral-text-secondary font-medium
            transition-all duration-200 hover:text-blue-700 group
          "
          title="切換至教師視角"
        >
          <div className="w-10 h-10 rounded-xl bg-white border border-gray-200 shadow-sm flex items-center justify-center transition-all duration-200 group-hover:bg-blue-50 group-hover:border-blue-200">
            <FaChalkboardTeacher className="w-5 h-5 flex-shrink-0 group-hover:scale-110 transition-transform" />
          </div>
          <span className="max-lg:hidden whitespace-nowrap">切換至教師視角</span>
        </button>
      );
    }

    return () => {
      if (setHeaderActions) setHeaderActions(null);
    };
  }, [user, setHeaderActions, navigate]);

  const handleJoinCourse = async () => {
    if (!joinCode.trim()) {
      setToast({ show: true, message: '請輸入課程代碼', type: 'error' });
      return;
    }

    try {
      setIsJoining(true);

      // 寫入操作前先跟後端核對目前 token 真正屬於誰，
      // 避免其他分頁登入別的帳號、還沒同步完成前就誤加到錯的帳號
      const currentUser = await refreshAuthenticatedUser();
      if (!currentUser || String(currentUser.user_id) !== String(user?.user_id)) {
        setToast({
          show: true,
          message: '偵測到登入身分已變更，畫面已更新，請確認目前帳號後再試一次',
          type: 'error'
        });
        return;
      }

      const result = await joinCourse(joinCode);
      setToast({ show: true, message: `成功加入課程：${result.course_name}`, type: 'success' });
      setShowJoinModal(false);
      setJoinCode('');

      // Invalidate queries to trigger refresh
      queryClient.invalidateQueries({ queryKey: ['enrolled-courses'] });
    } catch (err: any) {
      setToast({ show: true, message: err.message || '加入課程失敗', type: 'error' });
    } finally {
      setIsJoining(false);
    }
  };

  return (
    <div className="w-full min-h-full bg-transparent relative">
      <div className="relative z-10 px-20 py-12 space-y-12">
        <div className="flex-grow">
          {/* ... existing content ... */}
          <div>
            {/* Welcome Section */}
            <div className="mb-8">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center text-white shadow-lg shadow-blue-600/30">
                  <FaUserGraduate size={22} />
                </div>
                <div>
                  <div className="text-xs text-neutral-text-secondary font-medium">歡迎回來，</div>
                  <h2 className="text-2xl font-bold bg-gradient-to-r from-theme-gradient-start via-theme-gradient-middle to-theme-gradient-end bg-clip-text text-transparent">
                    {user?.full_name} 同學
                  </h2>
                </div>
              </div>
              <p className="text-sm text-neutral-text-secondary leading-relaxed ml-0">
                很高興見到你，讓我們一起開啟今天的學習之旅！
              </p>
            </div>

            {/* Page Header */}
            <div className="mb-10">
              <div className="flex items-center gap-6">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center text-white shadow-lg shadow-blue-600/20">
                    <FaBookOpen size={20} />
                  </div>
                  <h1 className="text-2xl font-bold text-neutral-text-main tracking-tight">我的課程</h1>
                </div>

                <button
                  onClick={() => setShowJoinModal(true)}
                  className="bg-gradient-to-br from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white px-6 py-2.5 rounded-xl flex items-center gap-2 text-sm font-bold transition-all shadow-lg shadow-blue-600/20 active:scale-95"
                >
                  <FaPlus size={14} />
                  加入課程
                </button>
              </div>
            </div>

            {isLoading ? (
              <div className="flex justify-center py-12">
                <Spinner />
              </div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 text-red-700 px-6 py-4 rounded-xl shadow-sm">
                {error}
              </div>
            ) : courses.length === 0 ? (
              <div className="text-center py-16 text-neutral-text-secondary bg-white rounded-xl shadow-sm border border-neutral-border mb-10">
                <p className="text-lg">目前沒有課程</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 mb-10">
                {courses.map((course) => (
                  <Link
                    to={course.enrollment_role === 'ta' ? `/teacher/courses/${course.id}` : `/student/course/${course.id}`}
                    key={course.id}
                    className="
                      block 
                      bg-white
                      border border-neutral-border
                      rounded-xl
                      p-4
                      transition-shadow duration-300
                      no-underline 
                      text-neutral-text-main 
                      shadow-sm
                      hover:shadow-lg
                      group
                      relative
                      overflow-hidden
                      flex flex-col h-full
                    "
                  >
                    {/* Decorative gradient bar - kept but subtle */}
                    <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-600 to-blue-400 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>

                    <div className="flex items-center gap-3 mb-2">
                      <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-50 to-blue-100 flex items-center justify-center text-blue-700 flex-shrink-0">
                        <FaBookOpen size={20} />
                      </div>
                      <div className="flex-grow min-w-0">
                        <h4 className="text-xl font-bold text-gray-900 mb-0 truncate leading-tight group-hover:text-blue-700 transition-colors">
                          {course.name}
                        </h4>
                      </div>
                    </div>

                    <div className="space-y-2 mb-2 flex-grow">
                      <div className="flex items-center gap-2 text-sm text-neutral-text-secondary w-full">
                        <div className="flex items-center gap-2 min-w-0">
                          <FaUserGraduate className="text-neutral-icon flex-shrink-0" size={14} />
                          <span className="font-medium truncate">{course.teacher_name}</span>
                        </div>
                        {course.enrollment_role === 'ta' && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-700 border border-purple-200 ml-auto flex-shrink-0">
                            <FaUserShield size={10} />
                            助教
                          </span>
                        )}
                      </div>
                      {course.description && (
                        <div
                          className="text-sm text-neutral-text-secondary line-clamp-2 mt-2 leading-relaxed prose prose-sm max-w-none"
                          dangerouslySetInnerHTML={{ __html: course.description }}
                        />
                      )}
                    </div>

                    <div className="mt-auto flex justify-between items-center">
                      <p className="text-xs text-neutral-text-tertiary bg-gray-50 px-2 py-0.5 rounded-full inline-block mb-0">
                        {course.semester_name}
                      </p>
                      <div className="flex items-center gap-1 text-blue-700 text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                        <span>進入</span>
                        <FaChevronRight size={12} />
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}

            {/* Announcements Section */}
            <div className="mb-8">
              <div className="flex items-center gap-3 mb-6 border-b border-neutral-border pb-4">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center text-white shadow-lg shadow-blue-600/20">
                  <FaBell size={20} />
                </div>
                <h2 className="text-2xl font-bold text-neutral-text-main tracking-tight">最新公告</h2>
              </div>


              <div className="space-y-3">
                {announcements.map((announcement) => {
                  const isExpanded = expandedAnnouncements.includes(announcement.id);
                  return (
                    <div
                      key={announcement.id}
                      className={`rounded-xl border transition-all duration-200 overflow-hidden ${isExpanded ? 'border-blue-200 shadow-md transform -translate-y-0.5' : 'border-neutral-border hover:border-blue-300 shadow-sm bg-white'}`}
                    >
                      {/* Header - Always Visible */}
                      <div
                        className={`p-4 cursor-pointer flex items-center gap-4 transition-colors ${isExpanded ? 'bg-blue-50/50' : 'bg-transparent'}`}
                        onClick={() => {
                          setExpandedAnnouncements(prev =>
                            prev.includes(announcement.id)
                              ? prev.filter(id => id !== announcement.id)
                              : [...prev, announcement.id]
                          );
                        }}
                      >
                        <div className="flex-grow min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            {announcement.is_pinned && (
                              <FaThumbtack className="text-amber-500 -rotate-45 flex-shrink-0" size={14} />
                            )}
                            <h3 className={`font-semibold transition-colors ${isExpanded ? 'text-blue-700 font-bold' : 'text-neutral-text-main'}`}>
                              {announcement.title}
                            </h3>
                            {!announcement.is_visible && (
                              <span className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-50 text-red-600 border border-red-200 whitespace-nowrap leading-tight">
                                對學生隱藏中
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 text-sm text-neutral-text-tertiary">
                            <span className="font-medium text-blue-600/70">{announcement.course_name}</span>
                            <span>•</span>
                            <span>{formatDateTime(announcement.created_at)}</span>
                          </div>
                        </div>
                        <div className={`text-neutral-icon transition-transform duration-300 ${isExpanded ? 'rotate-180 text-blue-600' : ''}`}>
                          <FaChevronDown size={14} />
                        </div>
                      </div>

                      {/* Expanded Content */}
                      {isExpanded && (
                        <div className="px-10 py-5 bg-white border-t border-blue-100">
                          <div
                            className="text-sm text-neutral-text-main announcement-content"
                            dangerouslySetInnerHTML={{ __html: announcement.content }}
                          />
                          {/* Attachments */}
                          {announcement.attachments && announcement.attachments.length > 0 && (
                            <div className="mt-4 pt-4 border-t border-gray-100">
                              <p className="text-xs font-semibold text-neutral-text-tertiary uppercase tracking-wide mb-2">附件下載</p>
                              <div className="space-y-2">
                                {announcement.attachments.map((att) => (
                                  <a
                                    key={att.id}
                                    href={`${API_BASE_URL}${att.download_url}`}
                                    download
                                    className="flex items-center gap-3 px-3 py-2 rounded-lg border border-gray-200 bg-gray-50 hover:bg-blue-50 hover:border-blue-200 transition-colors group no-underline"
                                  >
                                    <div className={`flex-shrink-0 ${att.original_file_name.toLowerCase().endsWith('.pdf') ? 'text-red-500' :
                                      att.original_file_name.toLowerCase().endsWith('.doc') || att.original_file_name.toLowerCase().endsWith('.docx') ? 'text-blue-500' :
                                        att.original_file_name.toLowerCase().endsWith('.ppt') || att.original_file_name.toLowerCase().endsWith('.pptx') ? 'text-orange-500' :
                                          'text-gray-400'
                                      }`}>
                                      {att.original_file_name.toLowerCase().endsWith('.pdf') ? <FaFilePdf size={20} /> :
                                        (att.original_file_name.toLowerCase().endsWith('.doc') || att.original_file_name.toLowerCase().endsWith('.docx')) ? <FaFileWord size={20} /> :
                                          (att.original_file_name.toLowerCase().endsWith('.ppt') || att.original_file_name.toLowerCase().endsWith('.pptx')) ? <FaFilePowerpoint size={20} /> :
                                            <FaFileAlt size={20} />}
                                    </div>
                                    <div className="flex-grow min-w-0">
                                      <p className="text-sm font-medium text-neutral-text-main truncate group-hover:text-blue-700 transition-colors">
                                        {att.original_file_name}
                                      </p>
                                      <p className="text-xs text-neutral-text-tertiary">
                                        {att.file_size_bytes > 1024 * 1024
                                          ? `${(att.file_size_bytes / 1024 / 1024).toFixed(1)} MB`
                                          : `${Math.round(att.file_size_bytes / 1024)} KB`}
                                        {att.uploaded_at && ` · ${formatDateTime(att.uploaded_at)}`}
                                      </p>
                                    </div>
                                    <span className="text-xs text-blue-600 font-medium opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">下載</span>
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {announcements.length === 0 && (
                <div className="text-center py-8 text-neutral-text-tertiary bg-white rounded-xl shadow-sm border border-neutral-border">
                  目前沒有公告
                </div>
              )}
            </div>
          </div>
        </div>

      </div>

      <Modal
        isOpen={showJoinModal}
        onClose={() => setShowJoinModal(false)}
        title="加入新課程"
      >
        <div className="space-y-4">
          <p className="text-gray-600">請輸入老師提供的 8 位課程代碼：</p>
          <input
            type="text"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
            placeholder="例如: ABC12345"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all font-mono tracking-wider uppercase"
            maxLength={8}
          />
          <div className="flex justify-end gap-3 mt-6">
            <button
              onClick={() => setShowJoinModal(false)}
              className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleJoinCourse}
              disabled={isJoining || !joinCode}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium flex items-center gap-2"
            >
              {isJoining ? (
                <>
                  <Spinner />
                  <span className="ml-2">加入中...</span>
                </>
              ) : '確認加入'}
            </button>
          </div>
        </div>
      </Modal>

      {
        toast.show && (
          <Toast
            message={toast.message}
            type={toast.type}
            onClose={() => setToast({ ...toast, show: false })}
          />
        )
      }
    </div >
  );
}

export default Overview;