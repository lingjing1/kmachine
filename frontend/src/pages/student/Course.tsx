import { useState, useEffect, useMemo } from 'react';
import { useParams, Link, useOutletContext, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
   FaBell, FaChevronDown, FaChevronUp, FaBook, FaClipboardCheck,
   FaCheckCircle, FaFilePdf, FaFilePowerpoint, FaFileWord, FaFileAlt, FaEdit, FaListOl, FaChalkboardTeacher, FaLock, FaThumbtack
} from 'react-icons/fa';
import { FaBookOpenReader } from 'react-icons/fa6';
import { MdRateReview } from 'react-icons/md';
import Spinner from '../../components/common/Spinner';
import Tooltip from '../../components/common/Tooltip';
import { getSubtypeLabel, getFileIcon } from '../../utils/contentUtils';
import { formatDateTime } from '../../utils/dateUtils';
import { useUser } from '../../contexts/UserContext';
import API_BASE_URL from '../../config/api';
import {
   getStudentUnitContents,
   type StudentUnitContentsResponse,
   getCourseAnnouncements,
   getEnrolledCourses
} from '../../services/studentApi';

// Helper for Subtype Labels (Synced with teacher view)
// getSubtypeLabel and getFileIcon are imported from contentUtils.tsx

interface CourseUnit {
   id: number;
   name: string;
   topic_id: number;
   description?: string;
}

interface CourseDetail {
   id: number;
   title: string;
   description?: string;
   units: CourseUnit[];
}


// 根據附件副檔名回傳 icon 樣式 (對應 contentUtils.tsx 的顏色設計)
const getAttachmentIconStyle = (title: string): { bg: string; color: string } => {
   const name = (title || '').toLowerCase();
   if (name.endsWith('.pdf')) return { bg: 'bg-red-50', color: 'text-red-500' };
   if (name.endsWith('.ppt') || name.endsWith('.pptx')) return { bg: 'bg-orange-50', color: 'text-orange-600' };
   if (name.endsWith('.doc') || name.endsWith('.docx')) return { bg: 'bg-blue-50', color: 'text-blue-600' };
   if (name.endsWith('.xls') || name.endsWith('.xlsx')) return { bg: 'bg-green-50', color: 'text-green-600' };
   if (['.jpg', '.jpeg', '.png', '.gif', '.webp'].some(e => name.endsWith(e))) return { bg: 'bg-purple-50', color: 'text-purple-500' };
   if (['.txt', '.md', '.csv', '.log'].some(e => name.endsWith(e))) return { bg: 'bg-gray-50', color: 'text-gray-600' };
   return { bg: 'bg-gray-50', color: 'text-gray-500' };
};

const Course = () => {
   const { courseId } = useParams<{ courseId: string }>();
   const { user } = useUser();
   const navigate = useNavigate();
   const { setHeaderActions } = useOutletContext<any>() || {};
   // Queries using TanStack Query for deduplication
   const {
      data: course,
      isLoading: isCourseLoading,
      error: courseError
   } = useQuery<CourseDetail>({
      queryKey: ['course-detail', courseId],
      queryFn: async () => {
         const res = await fetch(`${API_BASE_URL}/api/courses/${courseId}`);
         if (!res.ok) throw new Error('無法取得課程資訊');
         return res.json();
      },
      enabled: !!courseId,
      staleTime: 5 * 60 * 1000,
   });

   const {
      data: announcements = []
   } = useQuery({
      queryKey: ['course-announcements', courseId],
      queryFn: () => getCourseAnnouncements(Number(courseId)),
      enabled: !!courseId,
      staleTime: 5 * 60 * 1000,
   });

   // Use the same query key as StudentSidebar so we share the cache
   const { data: coursesData } = useQuery({
      queryKey: ['enrolled-courses'], // Removed user_id as it's handled by JWT in studentApi
      queryFn: () => getEnrolledCourses(),
      enabled: !!user,
   });

   const isLoading = isCourseLoading; // Only block on main course data
   const error = courseError ? (courseError as Error).message : null;

   const [expandedWeeks, setExpandedWeeks] = useState<number[]>([]);
   const [expandedAnnouncements, setExpandedAnnouncements] = useState<number[]>([]);
   const [materialModes, setMaterialModes] = useState<Record<number, 'preview' | 'review'>>({});
   const [assignmentModes, setAssignmentModes] = useState<Record<number, 'homework' | 'exam'>>({});
   const [unitContents, setUnitContents] = useState<Record<number, StudentUnitContentsResponse>>({});
   const [loadingUnits, setLoadingUnits] = useState<Record<number, boolean>>({});

   // Check if the current user is a TA for this specific course
   const isCourseTA = useMemo(() => {
      return Array.isArray(coursesData)
         ? coursesData.some(
            (c: any) => String(c.id) === String(courseId) && c.enrollment_role === 'ta'
         )
         : false;
   }, [coursesData, courseId]);

   // Add Teacher View Button if user is teacher or TA for this course
   useEffect(() => {
      const isTeacherOrTA = user?.role === 'teacher' || isCourseTA;
      if (isTeacherOrTA && setHeaderActions) {
         setHeaderActions(
            <button
               onClick={() => navigate(`/teacher/courses/${courseId}`)}
               className="
                     flex items-center gap-2 text-neutral-text-secondary font-medium
                     transition-all duration-200 hover:text-blue-700 group
                   "
               title="切換至教師視角"
            >
               <div className="w-10 h-10 rounded-xl bg-white border border-gray-200 shadow-sm flex items-center justify-center transition-all duration-200 group-hover:bg-blue-50 group-hover:border-blue-200">
                  <FaChalkboardTeacher className="w-5 h-5 flex-shrink-0 group-hover:scale-110 transition-transform" />
               </div>
               <span className="max-lg:hidden whitespace-nowrap">
                  {isCourseTA ? '切換回助教視角' : '切換至教師視角'}
               </span>
            </button>
         );
      }

      return () => {
         if (setHeaderActions) setHeaderActions(null);
      };
   }, [user, courseId, setHeaderActions, navigate, isCourseTA]);

   // Reset all local states when switching between different courses
   useEffect(() => {
      if (courseId) {
         setExpandedWeeks([]);
         setExpandedAnnouncements([]);
         setMaterialModes({});
         setAssignmentModes({});
         setUnitContents({});
         setLoadingUnits({});
      }
   }, [courseId]);

   // Pre-load and expand only the LATEST unit when course data is loaded
   useEffect(() => {
      if (course?.units && course.units.length > 0 && expandedWeeks.length === 0) {
         // Find latest unit (highest topic_id)
         const sortedUnits = [...course.units].sort((a: CourseUnit, b: CourseUnit) => b.topic_id - a.topic_id);
         const latestUnit = sortedUnits[0];
         const topicIdsToExpand = [latestUnit.topic_id];

         setExpandedWeeks(topicIdsToExpand);

         // Initialize modes for this unit
         setMaterialModes(prev => ({ ...prev, [latestUnit.topic_id]: 'preview' }));
         setAssignmentModes(prev => ({ ...prev, [latestUnit.topic_id]: 'homework' }));

         // Scroll to latest unit
         setTimeout(() => {
            const el = document.getElementById(`student-unit-card-${latestUnit.topic_id}`);
            if (el) {
               el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
         }, 300);

         // Fetch contents for this unit immediately
         if (!unitContents[latestUnit.id] && !loadingUnits[latestUnit.id]) {
            const fetchLatestUnit = async () => {
               setLoadingUnits(prev => ({ ...prev, [latestUnit.id]: true }));
               try {
                  const contentsResult = await getStudentUnitContents(latestUnit.id);
                  setUnitContents(prev => ({ ...prev, [latestUnit.id]: contentsResult }));
               } catch (fetchErr) {
                  console.error("Failed to preload unit contents:", fetchErr);
               } finally {
                  setLoadingUnits(prev => ({ ...prev, [latestUnit.id]: false }));
               }
            };
            fetchLatestUnit();
         }
      }
   }, [course, expandedWeeks.length, unitContents, loadingUnits]);

   const toggleWeek = async (topicId: number, unitId: number) => {
      const isCurrentlyExpanded = expandedWeeks.includes(topicId);

      setExpandedWeeks(prev =>
         isCurrentlyExpanded
            ? prev.filter(id => id !== topicId)
            : [...prev, topicId]
      );

      // Initialize modes when expanding if not set
      if (!materialModes[topicId]) {
         setMaterialModes(prev => ({ ...prev, [topicId]: 'preview' }));
         setAssignmentModes(prev => ({ ...prev, [topicId]: 'homework' }));
      }

      // Fetch unit contents from API when expanding (if not already loaded)
      if (!isCurrentlyExpanded && !unitContents[unitId] && !loadingUnits[unitId]) {
         console.log(`[API] Fetching contents for unit ${unitId}...`);
         setLoadingUnits(prev => ({ ...prev, [unitId]: true }));
         try {
            const contents = await getStudentUnitContents(unitId);
            console.log(`[API] Received contents for unit ${unitId}: `, contents);
            setUnitContents(prev => ({ ...prev, [unitId]: contents }));
         } catch (error) {
            console.error(`[API] Failed to fetch unit ${unitId} contents: `, error);
         } finally {
            setLoadingUnits(prev => ({ ...prev, [unitId]: false }));
         }
      } else {
         console.log(`[API] Skipping fetch for unit ${unitId}: expanded = ${isCurrentlyExpanded}, hasData = ${!!unitContents[unitId]}, loading = ${!!loadingUnits[unitId]}`);
      }
   };

   const setMaterialMode = (topicId: number, mode: 'preview' | 'review') => {
      setMaterialModes(prev => ({ ...prev, [topicId]: mode }));
   };

   const setAssignmentMode = (topicId: number, mode: 'homework' | 'exam') => {
      setAssignmentModes(prev => ({ ...prev, [topicId]: mode }));
   };

   if (isLoading) return <div className="flex justify-center py-12"><Spinner /></div>;
   if (error) return <div className="p-6 text-red-500 bg-red-50 rounded-lg mx-6 mt-6">{error}</div>;
   if (!course) return null;

   return (
      <div className="w-full min-h-full bg-transparent relative">
         {/* Localized Top Gradient - Removed in favor of global layout gradient */}

         <div className="relative z-10 p-6 space-y-8">

            {/* Announcement Section */}
            <div className="bg-white rounded-xl border border-neutral-border shadow-sm p-4 hover:shadow-md transition-shadow">
               <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 bg-blue-50 rounded-full">
                     <FaBell className="text-theme-primary" size={18} />
                  </div>
                  <h2 className="text-lg font-semibold text-neutral-text-main">最新公告</h2>
               </div>

               <div className="p-4 border-t border-neutral-border bg-gray-50/30">
                  {announcements.length > 0 ? (
                     <div className={`space-y-3 ${expandedAnnouncements.length > 0 ? '' : 'max-h-[220px] overflow-y-auto pr-1'}`}>
                        {announcements.map((announcement) => {
                           const isExpanded = expandedAnnouncements.includes(announcement.id);
                           return (
                              <div
                                 key={announcement.id}
                                 className={`rounded-xl border transition-all duration-200 overflow-hidden ${isExpanded ? 'border-blue-200 shadow-md transform -translate-y-0.5' : 'border-blue-100 hover:border-blue-300 hover:shadow-sm bg-blue-50/30'}`}
                              >
                                 {/* Header - Always Visible */}
                                 <div
                                    className={`p-4 cursor-pointer flex items-start gap-3 transition-colors ${isExpanded ? 'bg-blue-50/80' : 'bg-transparent'}`}
                                    onClick={() => {
                                       setExpandedAnnouncements(prev =>
                                          prev.includes(announcement.id)
                                             ? prev.filter(id => id !== announcement.id)
                                             : [...prev, announcement.id]
                                       );
                                    }}
                                 >
                                    <div className="flex-grow">
                                       <div className="flex items-center gap-2 mb-1">
                                          {announcement.is_pinned && (
                                             <FaThumbtack className="text-amber-500 -rotate-45 flex-shrink-0" size={14} />
                                          )}
                                          <h3 className={`text-base font-medium transition-colors ${isExpanded ? 'text-blue-700 font-bold' : 'text-neutral-text-main'}`}>
                                             {announcement.title}
                                          </h3>
                                          {!announcement.is_visible && (
                                             <span className="ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-50 text-red-600 border border-red-200 whitespace-nowrap leading-tight">
                                                對學生隱藏中
                                             </span>
                                          )}
                                       </div>



                                       <span className="text-xs text-neutral-text-tertiary block mt-2">
                                          {formatDateTime(announcement.created_at)}
                                       </span>
                                    </div>
                                    <div className={`text-neutral-text-tertiary transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`}>
                                       <FaChevronDown size={12} />
                                    </div>
                                 </div>

                                 {/* Expanded Content */}
                                 {isExpanded && (
                                    <div className="px-5 py-4 bg-white border-t border-blue-100">
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
                  ) : (
                     <div className="mt-4 text-center py-4 text-sm text-neutral-text-tertiary bg-gray-50 rounded-lg border border-gray-100">
                        本課程尚無公告
                     </div>
                  )}
               </div>
            </div>

            {/* Course Content Header */}
            <div>
               <h2 className="text-xl font-bold text-neutral-text-main mb-4">課程內容</h2>

               <div className="space-y-5">
                  {course.units.map((unit) => {
                     const isExpanded = expandedWeeks.includes(unit.topic_id);
                     const contents = unitContents[unit.id];
                     const isLoadingUnit = loadingUnits[unit.id];
                     const currentMatMode = materialModes[unit.topic_id] || 'preview';
                     const currentAssMode = assignmentModes[unit.topic_id] || 'homework';

                     // Filter content based on mode using API data
                     // New structure: contents.items (Array of StudentContentItem)
                     // Logic: 
                     // - 'preview' mode: show 'preview' items AND items without subtype (uploaded files, generic content)
                     // - 'review' mode: show 'review' items AND items without subtype
                     const filteredMaterials = (contents?.items || []).filter(item => {
                        // Only material types
                        if (item.content_type !== 'material') return false;

                        const isAttachment = item.content_subtype === 'attachment';

                        // In preview mode: show preview items OR items without subtype OR attachments
                        if (currentMatMode === 'preview') {
                           return item.content_subtype === 'preview' || !item.content_subtype || isAttachment;
                        }
                        // In review mode: show review items OR items without subtype OR exercise items OR attachments
                        return item.content_subtype === 'review' || !item.content_subtype || item.content_subtype === 'exercise' || isAttachment;
                     });

                     const filteredQuizzes = (contents?.items || []).filter(item => {
                        if (currentAssMode === 'homework') {
                           if (item.content_type === 'assignment') return true;
                           if (item.content_type === 'exam' && item.content_subtype === 'homework') return true;
                           return false;
                        }

                        if (currentAssMode === 'exam') {
                           if (item.content_type !== 'exam') return false;
                           return !item.content_subtype || ['quiz', 'midterm', 'final'].includes(item.content_subtype);
                        }

                        return false;
                     });

                     // Calculate uncompleted counts for badges
                     const unitItems = contents?.items || [];
                     const incompletePreview = unitItems.filter(item =>
                        item.content_type === 'material' &&
                        (item.content_subtype === 'preview' || !item.content_subtype) &&
                        !item.is_preview_completed
                     ).length;

                     const incompleteReview = unitItems.filter(item =>
                        item.content_type === 'material' &&
                        (item.content_subtype === 'review' || !item.content_subtype || item.content_subtype === 'exercise') &&
                        !item.is_preview_completed
                     ).length;

                     const incompleteHomework = unitItems.filter(item => {
                        if (item.content_type === 'assignment') return !item.is_submitted;
                        if (item.content_type === 'exam' && item.content_subtype === 'homework') return !item.is_submitted;
                        return false;
                     }).length;

                     const incompleteExam = unitItems.filter(item =>
                        item.content_type === 'exam' &&
                        (!item.content_subtype || ['quiz', 'midterm', 'final'].includes(item.content_subtype)) &&
                        !item.is_submitted
                     ).length;

                     // DEBUG: Log filtering results
                     console.log(`[Unit ${unit.id}]Contents: `, contents);
                     console.log(`[Unit ${unit.id}]Mode: mat = ${currentMatMode}, ass = ${currentAssMode}`);
                     console.log(`[Unit ${unit.id}]Filtered: ${filteredMaterials.length} materials, ${filteredQuizzes.length} quizzes`);
                     if (contents?.items) {
                        console.log(`[Unit ${unit.id}] All items: `, contents.items.map(i => ({ type: i.content_type, subtype: i.content_subtype, title: i.title })));
                     }

                     return (
                        <div key={unit.id} id={`student-unit-card-${unit.topic_id}`} className="bg-white rounded-xl border border-transparent shadow-[0_4px_20px_rgba(0,0,0,0.05)] hover:shadow-[0_8px_30px_rgba(0,0,0,0.08)] transition-all duration-300">
                           {/* Unit Header */}
                           <div
                              className={`p-5 flex items-center justify-between cursor-pointer hover:bg-gray-50 transition-colors ${isExpanded ? 'rounded-t-xl' : 'rounded-xl'}`}
                              onClick={() => toggleWeek(unit.topic_id, unit.id)}
                           >
                              <div className="flex items-center gap-3">
                                 <h3 className={`text-lg font-bold transition-colors ${isExpanded ? 'text-blue-700' : 'text-neutral-text-main'}`}>
                                    章節 {unit.topic_id}: {unit.name}
                                 </h3>
                              </div>
                              <div className="text-neutral-text-tertiary">
                                 {isExpanded ? <FaChevronUp /> : <FaChevronDown />}
                              </div>
                           </div>

                           {/* Unit Content */}
                           {isExpanded && (
                              <div className="px-6 pb-6 pt-4 border-t border-neutral-border/50 bg-gray-50/30 rounded-b-xl">

                                 <div
                                    className="text-neutral-text-secondary mb-6 text-sm prose prose-sm max-w-none"
                                    dangerouslySetInnerHTML={{ __html: unit.description || "學習單元相關內容說明..." }}
                                 />

                                 <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    {/* ==================== Materials Section (教材) ==================== */}
                                    <div className="bg-white rounded-xl border border-neutral-border p-5 shadow-sm hover:shadow-md transition-all duration-200 group flex flex-col h-full">
                                       <div className="flex items-center justify-between mb-4">
                                          <div className="flex items-center gap-2">
                                             <div className="p-2 bg-blue-50 text-theme-primary rounded-lg">
                                                <FaBook size={16} />
                                             </div>
                                             <h4 className="font-bold text-neutral-text-main text-lg">教材</h4>
                                             <span className="text-xs font-medium bg-gray-100 text-neutral-text-secondary px-2 py-0.5 rounded-full">
                                                {filteredMaterials.length}
                                             </span>
                                          </div>
                                          <div className="flex items-center">
                                             <button
                                                onClick={(e) => { e.stopPropagation(); setMaterialMode(unit.topic_id, 'preview'); }}
                                                className={`relative px-4 py-1.5 rounded-full text-sm font-bold flex items-center gap-1.5 transition-all ${currentMatMode === 'preview'
                                                   ? 'bg-blue-50 text-theme-primary'
                                                   : 'text-neutral-text-tertiary hover:bg-gray-50'
                                                   }`}
                                             >
                                                <FaBookOpenReader size={12} /> 課前預習
                                                {incompletePreview > 0 && (
                                                   <span className="absolute -top-1 -right-1 flex items-center justify-center min-w-[17px] h-[17px] px-1 bg-red-500 text-white text-[10px] font-bold rounded-full border border-white shadow-sm">
                                                      {incompletePreview}
                                                   </span>
                                                )}
                                             </button>
                                             <div className="w-px h-4 bg-gray-200 mx-1.5"></div>
                                             <button
                                                onClick={(e) => { e.stopPropagation(); setMaterialMode(unit.topic_id, 'review'); }}
                                                className={`relative px-4 py-1.5 rounded-full text-sm font-bold flex items-center gap-1.5 transition-all ${currentMatMode === 'review'
                                                   ? 'bg-blue-50 text-theme-primary'
                                                   : 'text-neutral-text-tertiary hover:bg-gray-50'
                                                   }`}
                                             >
                                                <MdRateReview size={12} /> 課後複習
                                                {incompleteReview > 0 && (
                                                   <span className="absolute -top-1 -right-1 flex items-center justify-center min-w-[17px] h-[17px] px-1 bg-red-500 text-white text-[10px] font-bold rounded-full border border-white shadow-sm">
                                                      {incompleteReview}
                                                   </span>
                                                )}
                                             </button>
                                          </div>
                                       </div>



                                       {/* Material List */}
                                       <div className="space-y-2 flex-grow">

                                          {isLoadingUnit ? (
                                             <div className="text-center py-6">
                                                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-theme-primary mx-auto"></div>
                                                <p className="text-xs text-neutral-text-tertiary mt-2">載入中...</p>
                                             </div>
                                          ) : filteredMaterials.length > 0 ? (
                                             (() => {
                                                const sequentialMaterials = filteredMaterials.filter(m => m.content_subtype !== 'attachment');
                                                let sequentialCounter = 0;

                                                return filteredMaterials.map((material) => {
                                                   // Determine icon and label
                                                   const isAttachment = material.content_subtype === 'attachment';
                                                   const isLocked = isAttachment && !material.is_preview_completed;

                                                   if (!isAttachment) {
                                                      sequentialCounter++;
                                                   }

                                                   // 圖示樣式：鎖定=灰色, 未鎖定附件=彩色, 非附件=主題色
                                                   const iconStyle = (() => {
                                                      if (isLocked) return { bg: 'bg-gray-100', color: 'text-gray-400' };
                                                      if (isAttachment) return getAttachmentIconStyle(material.title);
                                                      return material.is_preview_completed
                                                         ? { bg: 'bg-blue-50', color: 'text-theme-primary' }
                                                         : { bg: 'bg-gray-100', color: 'text-gray-400' };
                                                   })();
                                                   const targetUrl = isAttachment
                                                      ? `/student/course/${courseId}/units/${unit.id}/attachment/${Math.abs(material.id)}`
                                                      : `/student/course/${courseId}/units/${unit.id}/preview?contentId=${material.id}${currentMatMode === 'review' ? '&stage=review' : ''}`;

                                                   const content = (
                                                      <Link
                                                         key={`mat-${material.id}`}
                                                         to={targetUrl}
                                                         className={`flex items-center gap-3 p-3 rounded-xl hover:bg-blue-50/50 border border-transparent hover:border-blue-100 transition-all cursor-pointer group/item ${isLocked ? 'grayscale opacity-50 cursor-not-allowed pointer-events-none' : ''}`}
                                                         state={{
                                                            title: material.title,
                                                            fileType: (material.content as any)?.file_type,
                                                            itemIndex: !isAttachment ? sequentialCounter : null,
                                                            totalItems: sequentialMaterials.length,
                                                            materialsInSequence: sequentialMaterials.map(m => ({ id: m.id, title: m.title }))
                                                         }}
                                                         onClick={(e) => {
                                                            if (isLocked) {
                                                               e.preventDefault();
                                                            }
                                                         }}
                                                      >
                                                         <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${iconStyle.bg} ${iconStyle.color} ${!isLocked ? 'border border-blue-100' : ''}`}>
                                                            {isAttachment ? (
                                                               getFileIcon('file', material.title, 12, "flex items-center justify-center")
                                                            ) : (
                                                               material.display_order || sequentialCounter
                                                            )}
                                                         </div>
                                                         <div className="flex-grow min-w-0">
                                                            <div className="text-sm font-medium text-neutral-text-main group-hover/item:text-theme-primary transition-colors truncate flex items-center gap-2">
                                                               {material.title || material.knowledge_points?.[0]?.name}
                                                               {material.is_expired && (
                                                                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-gray-100 text-gray-500 border border-gray-200 whitespace-nowrap leading-tight">
                                                                     期限截止
                                                                  </span>
                                                               )}
                                                               {!material.is_visible && (
                                                                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-50 text-red-600 border border-red-200 whitespace-nowrap leading-tight">
                                                                     對學生隱藏中
                                                                  </span>
                                                               )}
                                                            </div>
                                                            <div className="text-xs text-neutral-text-tertiary">
                                                               {isAttachment ? '單元附件' : getSubtypeLabel('material', material.content_subtype)}
                                                            </div>
                                                         </div>
                                                         {material.is_preview_completed && !isAttachment && (
                                                            <FaCheckCircle size={16} className="text-theme-primary" />
                                                         )}
                                                         {isLocked && (
                                                            <div className="p-1 rounded bg-gray-100">
                                                               <FaLock size={12} className="text-gray-400" />
                                                            </div>
                                                         )}
                                                      </Link>
                                                   );

                                                   if (isLocked) {
                                                      return (
                                                         <Tooltip key={`mat-${material.id}`} content="閱讀完以上教材後解鎖" position="top">
                                                            {content}
                                                         </Tooltip>
                                                      );
                                                   }

                                                   return content;
                                                });
                                             })()
                                          ) : (
                                             !currentMatMode || currentMatMode === 'preview' ? (
                                                <div className="text-center py-6 text-neutral-text-tertiary text-sm italic">
                                                   沒有{currentMatMode === 'preview' ? '預習' : '複習'}教材
                                                </div>
                                             ) : null
                                          )}
                                       </div>
                                    </div>

                                    {/* ==================== Assignments Section (作業) -> 測驗 ==================== */}
                                    <div className="bg-white rounded-xl border border-neutral-border p-5 shadow-sm hover:shadow-md transition-all duration-200 group flex flex-col h-full overflow-visible">
                                       <div className="flex items-center justify-between mb-4">
                                          <div className="flex items-center gap-2">
                                             <div className="p-2 bg-blue-50 text-theme-primary rounded-lg">
                                                <FaListOl size={16} />
                                             </div>
                                             <h4 className="font-bold text-neutral-text-main text-lg">試卷</h4>
                                             <span className="text-xs font-medium bg-gray-100 text-neutral-text-secondary px-2 py-0.5 rounded-full">
                                                {filteredQuizzes.length}
                                             </span>
                                          </div>

                                          {/* Filter Buttons */}
                                          <div className="flex items-center">
                                             <button
                                                onClick={(e) => { e.stopPropagation(); setAssignmentMode(unit.topic_id, 'homework'); }}
                                                className={`relative px-4 py-1.5 rounded-full text-sm font-bold flex items-center gap-1.5 transition-all ${currentAssMode === 'homework'
                                                   ? 'bg-blue-50 text-theme-primary'
                                                   : 'text-neutral-text-tertiary hover:bg-gray-50'
                                                   }`}
                                             >
                                                <FaEdit size={12} /> 作業
                                                {incompleteHomework > 0 && (
                                                   <span className="absolute -top-1 -right-1 flex items-center justify-center min-w-[17px] h-[17px] px-1 bg-red-500 text-white text-[10px] font-bold rounded-full border border-white shadow-sm">
                                                      {incompleteHomework}
                                                   </span>
                                                )}
                                             </button>
                                             <div className="w-px h-4 bg-gray-200 mx-1.5"></div>
                                             <button
                                                onClick={(e) => { e.stopPropagation(); setAssignmentMode(unit.topic_id, 'exam'); }}
                                                className={`relative px-4 py-1.5 rounded-full text-sm font-bold flex items-center gap-1.5 transition-all ${currentAssMode === 'exam'
                                                   ? 'bg-blue-50 text-theme-primary'
                                                   : 'text-neutral-text-tertiary hover:bg-gray-50'
                                                   }`}
                                             >
                                                <FaClipboardCheck size={12} /> 考試
                                                {incompleteExam > 0 && (
                                                   <span className="absolute -top-1 -right-1 flex items-center justify-center min-w-[17px] h-[17px] px-1 bg-red-500 text-white text-[10px] font-bold rounded-full border border-white shadow-sm">
                                                      {incompleteExam}
                                                   </span>
                                                )}
                                             </button>
                                          </div>
                                       </div>

                                       {/* Quiz List */}
                                       <div className="space-y-2 flex-grow">
                                          {isLoadingUnit ? (
                                             <div className="text-center py-6">
                                                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-theme-primary mx-auto"></div>
                                                <p className="text-xs text-neutral-text-tertiary mt-2">載入中...</p>
                                             </div>
                                          ) : filteredQuizzes.length > 0 ? (
                                             filteredQuizzes.map((quiz) => {
                                                // Map subtype to display label

                                                return (
                                                   <Link
                                                      key={`quiz-${quiz.id}`}
                                                      to={`/student/course/${courseId}/units/${unit.id}/preview?contentId=${quiz.id}`}
                                                      className="flex items-center gap-3 p-3 rounded-xl hover:bg-blue-50/50 border border-transparent hover:border-blue-100 transition-all cursor-pointer group/item"
                                                   >
                                                      <div className={`p-1.5 rounded-md flex items-center justify-center transition-colors ${quiz.is_submitted ? 'bg-blue-50 text-theme-primary' : 'bg-gray-100 text-gray-400'}`}>
                                                         {quiz.content_subtype === 'homework' ? <FaEdit size={14} /> : <FaClipboardCheck size={14} />}
                                                      </div>
                                                      <div className="flex-grow min-w-0">
                                                         <div className="text-sm font-medium text-neutral-text-main group-hover/item:text-theme-primary transition-colors truncate flex items-center gap-2">
                                                            {quiz.title || quiz.knowledge_points?.[0]?.name}
                                                            {quiz.is_expired && (
                                                               <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-gray-100 text-gray-500 border border-gray-200 whitespace-nowrap leading-tight">
                                                                  期限截止
                                                               </span>
                                                            )}
                                                            {!quiz.is_visible && (
                                                               <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-50 text-red-600 border border-red-200 whitespace-nowrap leading-tight">
                                                                  對學生隱藏中
                                                               </span>
                                                            )}
                                                         </div>
                                                         <div className="text-xs text-neutral-text-tertiary">{getSubtypeLabel('exam', quiz.content_subtype)}</div>
                                                      </div>
                                                      <div className="w-[16px] h-[16px] flex items-center justify-center">
                                                         {quiz.is_submitted && <FaCheckCircle size={16} className="text-theme-primary" />}
                                                      </div>
                                                   </Link>
                                                );
                                             })
                                          ) : (
                                             <div className="text-center py-6 text-neutral-text-tertiary text-sm italic">
                                                沒有相關測驗
                                             </div>
                                          )}
                                       </div>
                                    </div>
                                 </div>
                              </div>
                           )}
                        </div>
                     );
                  })}
               </div>
            </div>
         </div>
      </div>
   );
};

export default Course;
