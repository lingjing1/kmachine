import { useState, useEffect, useMemo, useRef } from 'react';
import { useParams, useNavigate, useLocation, useOutletContext } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useUser } from '../../contexts/UserContext';
import API_BASE_URL from '../../config/api';
import { FaListOl, FaChevronDown, FaArrowUp, FaArrowDown, FaMagic, FaBook, FaEdit, FaTrash, FaPlus, FaBell, FaFileAlt, FaClipboardCheck, FaEye, FaEyeSlash, FaCloudUploadAlt, FaHistory, FaThumbtack } from 'react-icons/fa';
import { FaBookOpenReader } from 'react-icons/fa6';
import { MdRateReview, MdAddLink } from 'react-icons/md';
import { RiLinkUnlinkM } from "react-icons/ri";
import { AiFillCopy } from "react-icons/ai";
import Tooltip from '../../components/common/Tooltip';
import Spinner from '../../components/common/Spinner';
import Modal from '../../components/common/Modal';
import WideModal from '../../components/common/WideModal';
import Button from '../../components/common/Button';
import RichTextEditor from '../../components/common/RichTextEditor';
import Toast from '../../components/common/Toast';
import ConfirmDialog from '../../components/common/ConfirmDialog';
import AttachmentList, { Attachment } from '../../components/common/AttachmentList';
import AttachmentUpload from '../../components/common/AttachmentUpload';
import MaterialSelectionModal from '../../components/common/MaterialSelectionModal';
import { GeneratedMaterialOption } from '../../components/common/MaterialSelectionView';
import FileSubmissionsPanel from '../../components/teacher/FileSubmissionsPanel';
import PrepGuide from '../../components/teacher/PrepGuide';
import { authClient } from '../../services/authClient';

// Type Definitions

export interface UnifiedContent {
    id: number;
    course_id: number;
    unit_id?: number | null;
    title: string;
    description?: string | null;
    content_type: 'material' | 'exam';
    content_subtype?: string | null;
    source_type: string;
    source_id: number;
    content?: any;
    is_visible?: boolean;
    created_at?: string;
    display_order?: number;
}

interface CourseUnit {
    id: number;
    course_id: number;
    topic_id: number;
    name: string;
    description?: string;
    materials?: UnifiedContent[];
    exams?: UnifiedContent[];
}

interface CourseDetail {
    id: number;
    name: string;
    semester_name: string;
    description: string | null;
    teacher_name: string;
    units: CourseUnit[];
}

interface ReferenceMaterial {
    id: number;
    file_name: string;
    unique_content_id: number;
    processing_status: 'pending' | 'in_progress' | 'completed' | 'failed' | undefined;
    created_at: string;
    file_type?: string;
    source_type?: string;
    file_path?: string;
    original_file_name?: string;
    file_size?: number;
}

// Helper for Subtype Labels
import { getSubtypeLabel, getFileIcon } from '../../utils/contentUtils';
import { formatDateTime } from '../../utils/dateUtils';

interface Announcement {
    id: number;
    course_id: number;
    title: string;
    content: string;
    author_id: number;
    is_pinned: boolean;
    is_visible: boolean;
    created_at: string;
    updated_at: string;
}

// ==================== Component ====================

function Courses() {
    const queryClient = useQueryClient();
    const { courseId } = useParams<{ courseId: string }>();
    const navigate = useNavigate();
    const location = useLocation();
    const { setHeaderActions } = useOutletContext<any>() || {};
    const { user } = useUser(); // 取得當前登入的使用者
    const getAuthHeaders = (): Record<string, string> => {
        const token = sessionStorage.getItem('access_token');
        return token ? { 'Authorization': `Bearer ${token}` } : {};
    };

    // Queries
    const { data: courseData, isLoading: isCourseLoading, error: courseError } = useQuery<CourseDetail>({
        queryKey: ['course', courseId],
        queryFn: async () => {
            const res = await fetch(`${API_BASE_URL}/api/courses/${courseId}`);
            if (!res.ok) throw new Error('API 無法連線');
            return res.json();
        },
        enabled: !!courseId
    });

    const { data: contentsData, isLoading: isContentsLoading } = useQuery<UnifiedContent[]>({
        queryKey: ['course-contents', courseId],
        queryFn: async () => {
            const res = await fetch(`${API_BASE_URL}/api/courses/${courseId}/contents`);
            if (!res.ok) throw new Error('API 無法連線');
            return res.json();
        },
        enabled: !!courseId
    });

    const { data: announcementsData, isLoading: isAnnouncementsLoading, error: announcementsError } = useQuery<Announcement[]>({
        queryKey: ['announcements', courseId],
        queryFn: async () => {
            console.log('Fetching announcements...', { courseId, API_BASE_URL });
            try {
                const res = await fetch(`${API_BASE_URL}/api/courses/${courseId}/announcements`);
                if (!res.ok) {
                    const errorText = await res.text();
                    console.error('Announcement fetch failed:', res.status, errorText);
                    throw new Error(`無法載入公告: ${res.status}`);
                }
                const data = await res.json();
                console.log('Announcements fetched successfully:', data);
                return data;
            } catch (err) {
                console.error('Announcement fetch error:', err);
                throw err;
            }
        },
        enabled: !!courseId,
    });

    const { data: referenceMaterials } = useQuery<ReferenceMaterial[]>({
        queryKey: ['materials', courseId],
        queryFn: async () => {
            const res = await fetch(`${API_BASE_URL}/api/v1/materials?course_id=${courseId}`);
            if (!res.ok) throw new Error('Failed to fetch materials');
            return res.json();
        },
        enabled: !!courseId,
        refetchInterval: (query) => {
            const data = query.state.data as ReferenceMaterial[] | undefined;
            if (data?.some(m => m.processing_status === 'in_progress' || m.processing_status === 'pending')) {
                return 3000;
            }
            return false;
        }
    });

    const { data: allGeneratedMaterials, isLoading: isGeneratedLoading, isFetching: isGeneratedFetching } = useQuery<GeneratedMaterialOption[]>({
        queryKey: ['all-generated-materials', courseId],
        queryFn: async () => {
            const res = await fetch(`${API_BASE_URL}/api/v1/generated_materials?course_id=${courseId}`, {
                headers: getAuthHeaders()
            });
            if (!res.ok) throw new Error('Failed to fetch generated materials');
            return res.json();
        },
        enabled: !!courseId,
    });

    // Computed State
    const course = useMemo(() => {
        if (!courseData) return null;
        const contents = contentsData || [];
        const unitsWithContent = courseData.units.map((unit: CourseUnit) => ({
            ...unit,
            materials: contents.filter((c: UnifiedContent) => c.unit_id === unit.id && c.content_type === 'material'),
            exams: contents.filter((c: UnifiedContent) => c.unit_id === unit.id && c.content_type === 'exam'),
        }));
        return { ...courseData, units: unitsWithContent };
    }, [courseData, contentsData]);

    const announcements = announcementsData || [];
    const isLoading = isCourseLoading || isContentsLoading || isAnnouncementsLoading;

    if (announcementsError) {
        console.error('Error loading announcements:', announcementsError);
    }

    const error = courseError ? '無法載入課程資訊' : (announcementsError ? '無法載入公告' : null);

    const [expandedWeeks, setExpandedWeeks] = useState<number[]>([]);
    const hasInitializedRef = useRef(false);

    // Reset initialization when course changes
    useEffect(() => {
        hasInitializedRef.current = false;
        setExpandedWeeks([]);
    }, [courseId]);

    // Initial Side Effects
    useEffect(() => {
        if (courseData && courseData.units && !hasInitializedRef.current && courseId === String(courseData.id)) {
            // Find latest unit (highest topic_id)
            const sortedUnits = [...courseData.units].sort((a: CourseUnit, b: CourseUnit) => b.topic_id - a.topic_id);
            if (sortedUnits.length > 0) {
                const latestTopicId = sortedUnits[0].topic_id;
                setExpandedWeeks([latestTopicId]);

                // Scroll to latest unit
                setTimeout(() => {
                    const el = document.getElementById(`unit-card-${latestTopicId}`);
                    if (el) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }, 300);
            }
            hasInitializedRef.current = true;
        }
    }, [courseData, courseId]);

    // Update Header Actions and Breadcrumbs
    useEffect(() => {
        if (course && setHeaderActions) {
            if (user) {
                setHeaderActions(
                    <button
                        onClick={() => navigate(`/student/course/${courseId}`)}
                        className="
                            flex items-center gap-2 text-neutral-text-secondary font-medium
                            transition-all duration-200 hover:text-blue-700 group
                        "
                        title="切換至學生視角"
                    >
                        <div className="w-10 h-10 rounded-xl bg-white border border-gray-200 shadow-sm flex items-center justify-center transition-all duration-200 group-hover:bg-blue-50 group-hover:border-blue-200">
                            <FaEye className="w-5 h-5 flex-shrink-0 group-hover:scale-110 transition-transform" />
                        </div>
                        <span className="max-lg:hidden whitespace-nowrap">切換至學生視角</span>
                    </button>
                );
            }
        }
        return () => {
            if (setHeaderActions) setHeaderActions(null);
        };
    }, [course, courseId, setHeaderActions]);

    // Detect navigation from ContentEditor with refresh flag
    useEffect(() => {
        const state = location.state as any;
        if (state?.refresh && courseId) {
            // Invalidate cache to force re-fetch of updated content
            queryClient.invalidateQueries({ queryKey: ['course-contents', courseId] });
            // Clear the state to prevent repeated invalidation
            navigate(location.pathname, { replace: true, state: {} });
        }
    }, [location, courseId, queryClient, navigate]);

    // Derived Attachments (simplified)
    useEffect(() => {
        if (courseData?.units) {
            const attachmentsMap: Record<number, Attachment[]> = {};
            courseData.units.forEach((u: any) => {
                if (u.attachments) {
                    attachmentsMap[u.id] = u.attachments;
                }
            });
            setUnitAttachments(attachmentsMap);
        }
    }, [courseData]);

    // Modal states
    const [isAnnouncementModalOpen, setIsAnnouncementModalOpen] = useState(false);
    const [isCodeModalOpen, setIsCodeModalOpen] = useState(false);
    const [isEditAnnouncementModalOpen, setIsEditAnnouncementModalOpen] = useState(false);
    const [isTopicModalOpen, setIsTopicModalOpen] = useState(false);
    const [isEditChapterModalOpen, setIsEditChapterModalOpen] = useState(false);
    // Unified Add Content Modal State
    const [isAddContentModalOpen, setIsAddContentModalOpen] = useState(false);
    const [addContentTarget, setAddContentTarget] = useState<{ type: 'material' | 'exam', unitId: number } | null>(null);
    const [activeAddTab, setActiveAddTab] = useState<'uploaded' | 'generated'>('uploaded');
    const [selectedReferenceIds, setSelectedReferenceIds] = useState<number[]>([]);
    // const [allContents, setAllContents] = useState<UnifiedContent[]>([]); // Derived from query now
    const [isUploading, setIsUploading] = useState(false);


    // Form states
    const [newAnnouncement, setNewAnnouncement] = useState({ title: '', content: '' });
    const [editingAnnouncement, setEditingAnnouncement] = useState<Announcement | null>(null);
    const [newChapter, setNewChapter] = useState({ chapter_number: 1, chapter_name: '', description: '' });
    const [editingChapter, setEditingChapter] = useState<CourseUnit | null>(null);

    // Announcements state
    // const [announcements, setAnnouncements] = useState<Announcement[]>([]); // Derived from query now
    const [expandedAnnouncements, setExpandedAnnouncements] = useState<number[]>([]);

    // Attachments state
    const [announcementAttachments, setAnnouncementAttachments] = useState<Record<number, Attachment[]>>({});
    const [pendingAnnouncementAttachments, setPendingAnnouncementAttachments] = useState<File[]>([]);
    const [unitAttachments, setUnitAttachments] = useState<Record<number, Attachment[]>>({});
    const [pendingUnitAttachments, setPendingUnitAttachments] = useState<File[]>([]);

    // Enrollment Code state
    const [enrollmentCode, setEnrollmentCode] = useState<{
        code: string;
        expires_at: string;
        is_expired: boolean;
    } | null>(null);

    // Toast state
    const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'error' | 'info' }>(
        { show: false, message: '', type: 'success' }
    );

    // Confirm dialog states
    const [confirmDialog, setConfirmDialog] = useState<{
        show: boolean;
        type: 'announcement' | 'chapter' | 'content' | 'attachment' | 'unit_attachment' | null;
        id: number | null;
        parentId?: number | null;
    }>({ show: false, type: null, id: null });


    // Tab states per unit
    const [materialTabs, setMaterialTabs] = useState<Record<number, 'preview' | 'review'>>({});
    const [paperTabs, setPaperTabs] = useState<Record<number, 'homework' | 'exam'>>({});

    const handleReorderContent = async (unitId: number, subtype: string | null, orderedIds: number[]) => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/courses/${courseId}/contents/reorder`, {
                method: 'POST',
                headers: {
                    ...getAuthHeaders(),
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    unit_id: unitId,
                    content_subtype: subtype,
                    ordered_ids: orderedIds
                })
            });

            if (!res.ok) throw new Error('排序失敗');

            setToast({ show: true, message: '已更新排序', type: 'success' });
            queryClient.invalidateQueries({ queryKey: ['course-contents', courseId] });
        } catch (err) {
            console.error('Reorder error:', err);
            setToast({ show: true, message: '更新排序失敗', type: 'error' });
        }
    };

    const moveContent = (unitId: number, _contentType: 'material' | 'exam', currentSubtype: string | null, currentIdx: number, direction: 'up' | 'down', list: UnifiedContent[]) => {
        const newItems = [...list];
        if (direction === 'up' && currentIdx > 0) {
            [newItems[currentIdx], newItems[currentIdx - 1]] = [newItems[currentIdx - 1], newItems[currentIdx]];
        } else if (direction === 'down' && currentIdx < newItems.length - 1) {
            [newItems[currentIdx], newItems[currentIdx + 1]] = [newItems[currentIdx + 1], newItems[currentIdx]];
        } else {
            return;
        }

        handleReorderContent(unitId, currentSubtype, newItems.map(item => item.id));
    };


    // File submissions modal state
    const [fileSubmissionsModal, setFileSubmissionsModal] = useState<{
        show: boolean;
        contentId: number | null;
        contentTitle: string;
    }>({ show: false, contentId: null, contentTitle: '' });









    // Enrollment Code Effect
    useEffect(() => {
        if (courseId) fetchEnrollmentCode();
    }, [courseId]);

    const toggleWeek = (week: number) => {
        setExpandedWeeks(prev =>
            prev.includes(week)
                ? prev.filter(w => w !== week)
                : [...prev, week]
        );
    };

    // ==================== Handler Functions ====================

    const handleAddAnnouncement = async () => {
        if (!courseId || !user) return;

        try {
            const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/announcements`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders()
                },
                body: JSON.stringify({
                    title: newAnnouncement.title,
                    content: newAnnouncement.content,
                    author_id: user.user_id
                })
            });

            if (response.ok) {
                const newItem = await response.json();
                queryClient.invalidateQueries({ queryKey: ['announcements', courseId] });

                // 如果有待上傳的附件，立即上傳
                if (pendingAnnouncementAttachments.length > 0) {
                    for (const file of pendingAnnouncementAttachments) {
                        try {
                            await handleUploadAttachment(newItem.id, file);
                        } catch (err) {
                            console.error('上傳附件失敗:', err);
                        }
                    }
                    setPendingAnnouncementAttachments([]);
                }

                setNewAnnouncement({ title: '', content: '' });
                setIsAnnouncementModalOpen(false);
                setToast({ show: true, message: '公告已新增', type: 'success' });
            } else {
                setToast({ show: true, message: '新增公告失敗', type: 'error' });
            }
        } catch (err) {
            setToast({ show: true, message: '新增公告錯誤', type: 'error' });
            console.error('新增公告錯誤:', err);
        }
    };

    const handleDeleteAnnouncement = async (id: number) => {
        if (!courseId) return;

        try {
            const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/announcements/${id}`, {
                method: 'DELETE',
                headers: getAuthHeaders()
            });

            if (response.ok) {
                queryClient.invalidateQueries({ queryKey: ['announcements', courseId] });
                setToast({ show: true, message: '公告已刪除', type: 'success' });
                setConfirmDialog({ show: false, type: null, id: null });
            } else {
                setToast({ show: true, message: '刪除公告失敗', type: 'error' });
            }
        } catch (err) {
            setToast({ show: true, message: '刪除公告錯誤', type: 'error' });
            console.error('刪除公告錯誤:', err);
        }
    };

    const handleEditAnnouncement = (announcement: Announcement) => {
        setEditingAnnouncement(announcement);
        setNewAnnouncement({ title: announcement.title, content: announcement.content });
        setIsEditAnnouncementModalOpen(true);
        // 載入該公告的附件
        fetchAnnouncementAttachments(announcement.id);
    };


    const handleTogglePin = async (announcement: Announcement) => {
        if (!courseId) return;
        try {
            const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/announcements/${announcement.id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders()
                },
                body: JSON.stringify({ is_pinned: !announcement.is_pinned })
            });

            if (response.ok) {
                queryClient.invalidateQueries({ queryKey: ['announcements', courseId] });
                setToast({ show: true, message: announcement.is_pinned ? '已取消置頂' : '已置頂公告', type: 'success' });
            } else {
                setToast({ show: true, message: '操作失敗', type: 'error' });
            }
        } catch (err) {
            console.error('Toggle pin error:', err);
            setToast({ show: true, message: '錯誤', type: 'error' });
        }
    };

    const handleToggleVisibility = async (announcement: Announcement) => {
        if (!courseId) return;
        try {
            const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/announcements/${announcement.id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders()
                },
                body: JSON.stringify({ is_visible: !announcement.is_visible })
            });

            if (response.ok) {
                queryClient.invalidateQueries({ queryKey: ['announcements', courseId] });
                setToast({ show: true, message: announcement.is_visible ? '公告已隱藏' : '公告已對學生顯示', type: 'success' });
            } else {
                setToast({ show: true, message: '操作失敗', type: 'error' });
            }
        } catch (err) {
            console.error('Toggle visibility error:', err);
            setToast({ show: true, message: '錯誤', type: 'error' });
        }
    };

    const handleUpdateAnnouncement = async () => {
        if (!editingAnnouncement || !courseId) return;

        try {
            const response = await fetch(
                `${API_BASE_URL}/api/courses/${courseId}/announcements/${editingAnnouncement.id}`,
                {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({
                        title: newAnnouncement.title,
                        content: newAnnouncement.content
                    })
                }
            );

            if (response.ok) {
                // const updatedAnnouncement = await response.json();
                queryClient.invalidateQueries({ queryKey: ['announcements', courseId] });

                // 如果有待上傳的附件，立即上傳
                if (pendingAnnouncementAttachments.length > 0) {
                    for (const file of pendingAnnouncementAttachments) {
                        try {
                            await handleUploadAttachment(editingAnnouncement.id, file);
                        } catch (err) {
                            console.error('上傳附件失敗:', err);
                        }
                    }
                    setPendingAnnouncementAttachments([]);
                }

                setNewAnnouncement({ title: '', content: '' });
                setEditingAnnouncement(null);
                setIsEditAnnouncementModalOpen(false);
                setToast({ show: true, message: '公告已更新', type: 'success' });
            } else {
                setToast({ show: true, message: '更新公告失敗', type: 'error' });
            }
        } catch (err) {
            setToast({ show: true, message: '更新公告錯誤', type: 'error' });
            console.error('更新公告錯誤:', err);
        }
    };



    const handleEditChapter = (chapter: CourseUnit) => {
        setEditingChapter(chapter);
        setNewChapter({
            chapter_number: chapter.topic_id,
            chapter_name: chapter.name,
            description: chapter.description || ''
        });
        setIsEditChapterModalOpen(true);
        // 載入該單元的附件
        fetchUnitAttachments(chapter.id);
    };

    // ==================== Navigation Handlers ====================





    // ==================== Enrollment Code Handlers ====================

    const fetchEnrollmentCode = async () => {
        if (!courseId) return;
        try {
            const response = await fetch(`${API_BASE_URL}/api/teacher/courses/${courseId}/enrollment-code`);
            if (response.ok) {
                const data = await response.json();
                setEnrollmentCode({
                    code: data.enrollment_code,
                    expires_at: data.expires_at,
                    is_expired: data.is_expired
                });
            } else if (response.status === 404) {
                // 404 means no code generated yet, clear the state
                setEnrollmentCode(null);
            } else {
                console.warn('Failed to fetch enrollment code');
            }
        } catch (err) {
            console.warn('Network error fetching enrollment code:', err);
        }
    };

    const handleGenerateEnrollmentCode = async () => {
        if (!courseId) return;
        try {
            const response = await fetch(`${API_BASE_URL}/api/teacher/courses/${courseId}/enrollment-code`, {
                method: 'POST',
                headers: getAuthHeaders()
            });
            if (response.ok) {
                const data = await response.json();
                setEnrollmentCode({
                    code: data.enrollment_code,
                    expires_at: data.expires_at,
                    is_expired: data.is_expired
                });
                setToast({ show: true, message: '課程碼已產生', type: 'success' });
            } else {
                setToast({ show: true, message: '產生課程碼失敗', type: 'error' });
            }
        } catch (err) {
            console.error(err);
            setToast({ show: true, message: '產生課程碼錯誤', type: 'error' });
        }
    };


    const fetchAnnouncementAttachments = async (announcementId: number) => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/announcement/${announcementId}/attachments`);
            if (response.ok) {
                const data = await response.json();
                setAnnouncementAttachments(prev => ({
                    ...prev,
                    [announcementId]: data
                }));
            }
        } catch (err) {
            console.error('載入附件失敗:', err);
        }
    };

    const handleUploadAttachment = async (announcementId: number, file: File) => {
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(`${API_BASE_URL}/api/announcement/${announcementId}/attachments`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: formData
            });

            if (response.ok) {
                setToast({ show: true, message: '附件上傳成功', type: 'success' });
                // 重新載入附件列表
                await fetchAnnouncementAttachments(announcementId);
            } else {
                const error = await response.json();
                throw new Error(error.detail || '上傳失敗');
            }
        } catch (err: any) {
            setToast({ show: true, message: err.message || '附件上傳失敗', type: 'error' });
            throw err;
        }
    };

    const handleDeleteAttachment = async (announcementId: number, attachmentId: number) => {
        setConfirmDialog({
            show: true,
            type: 'attachment',
            id: attachmentId,
            parentId: announcementId
        });
    };

    const executeDeleteAttachment = async (announcementId: number, attachmentId: number) => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/announcement/${announcementId}/attachments/${attachmentId}`, {
                method: 'DELETE',
                headers: getAuthHeaders()
            });

            if (response.ok) {
                setToast({ show: true, message: '附件已刪除', type: 'success' });
                // 重新載入附件列表
                await fetchAnnouncementAttachments(announcementId);
            } else {
                setToast({ show: true, message: '刪除附件失敗', type: 'error' });
            }
        } catch (err) {
            setToast({ show: true, message: '刪除附件錯誤', type: 'error' });
            console.error('刪除附件錯誤:', err);
        }
    };

    // ==================== Unit Attachment Handlers ====================

    const fetchUnitAttachments = async (unitId: number) => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/unit/${unitId}/attachments`);
            if (response.ok) {
                const data = await response.json();
                setUnitAttachments(prev => ({
                    ...prev,
                    [unitId]: data
                }));
            }
        } catch (err) {
            console.error('載入章節教材失敗:', err);
        }
    };

    const handleUploadUnitAttachment = async (unitId: number, file: File) => {
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(`${API_BASE_URL}/api/unit/${unitId}/attachments`, {
                method: 'POST',
                headers: getAuthHeaders(),
                body: formData
            });

            if (response.ok) {
                setToast({ show: true, message: '教材上傳成功', type: 'success' });
                await fetchUnitAttachments(unitId);
            } else {
                const error = await response.json();
                throw new Error(error.detail || '上傳失敗');
            }
        } catch (err: any) {
            setToast({ show: true, message: err.message || '教材上傳失敗', type: 'error' });
            throw err;
        }
    };

    const handleDeleteUnitAttachment = async (unitId: number, attachmentId: number) => {
        setConfirmDialog({
            show: true,
            type: 'unit_attachment',
            id: attachmentId,
            parentId: unitId
        });
    };

    const executeDeleteUnitAttachment = async (unitId: number, attachmentId: number) => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/unit/${unitId}/attachments/${attachmentId}`, {
                method: 'DELETE',
                headers: getAuthHeaders()
            });

            if (response.ok) {
                setToast({ show: true, message: '教材已刪除', type: 'success' });
                await fetchUnitAttachments(unitId);
            } else {
                setToast({ show: true, message: '刪除教材失敗', type: 'error' });
            }
        } catch (err) {
            setToast({ show: true, message: '刪除教材錯誤', type: 'error' });
            console.error('刪除教材錯誤:', err);
        }
    };

    // 當公告展開時載入附件
    useEffect(() => {
        expandedAnnouncements.forEach(announcementId => {
            if (!announcementAttachments[announcementId]) {
                fetchAnnouncementAttachments(announcementId);
            }
        });
    }, [expandedAnnouncements]);

    // ====================Chapter Handlers ====================

    const handleUpdateChapter = async () => {

        if (!editingChapter || !courseId) return;

        try {
            const response = await fetch(
                `${API_BASE_URL}/api/courses/${courseId}/units/${editingChapter.id}`,
                {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({
                        topic_id: newChapter.chapter_number,
                        name: newChapter.chapter_name,
                        description: newChapter.description
                    })
                }
            );

            if (response.ok) {
                queryClient.invalidateQueries({ queryKey: ['course', courseId] });
                setToast({ show: true, message: '章節已更新', type: 'success' });

                // 如果有待上傳的附件，立即上傳
                if (pendingUnitAttachments.length > 0) {
                    for (const file of pendingUnitAttachments) {
                        try {
                            await handleUploadUnitAttachment(editingChapter.id, file);
                        } catch (err) {
                            console.error('上傳單元附件失敗:', err);
                        }
                    }
                    setPendingUnitAttachments([]);
                }

                setNewChapter({ chapter_number: 1, chapter_name: '', description: '' });
                setEditingChapter(null);
                setIsEditChapterModalOpen(false);
            } else {
                setToast({ show: true, message: '更新章節失敗', type: 'error' });
                throw new Error('更新章節失敗');
            }
        } catch (err) {
            setToast({ show: true, message: '更新章節錯誤', type: 'error' });
            console.error('更新章節錯誤:', err);
            throw err;
        }
    };

    const handleDeleteChapter = async (id: number) => {
        if (!courseId) return;

        try {
            const response = await fetch(
                `${API_BASE_URL}/api/courses/${courseId}/units/${id}`,
                {
                    method: 'DELETE'
                }
            );

            if (response.ok) {
                queryClient.invalidateQueries({ queryKey: ['course', courseId] });
                setToast({ show: true, message: '章節已刪除', type: 'success' });
                setConfirmDialog({ show: false, type: null, id: null });
            } else {
                setToast({ show: true, message: '刪除章節失敗', type: 'error' });
            }
        } catch (err) {
            setToast({ show: true, message: '刪除章節錯誤', type: 'error' });
            console.error('刪除章節錯誤:', err);
        }
    };

    const handleAddChapter = async () => {
        if (!course || !courseId) return;

        try {
            const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/units`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders()
                },
                body: JSON.stringify({
                    topic_id: newChapter.chapter_number,
                    name: newChapter.chapter_name,
                    description: newChapter.description
                })
            });

            if (response.ok) {
                const newUnit = await response.json();
                queryClient.invalidateQueries({ queryKey: ['course', courseId] });

                // 如果有待上傳的附件，立即上傳
                if (pendingUnitAttachments.length > 0) {
                    for (const file of pendingUnitAttachments) {
                        try {
                            await handleUploadUnitAttachment(newUnit.id, file);
                        } catch (err) {
                            console.error('上傳單元附件失敗:', err);
                        }
                    }
                    setPendingUnitAttachments([]);
                }

                setNewChapter({ chapter_number: (course?.units?.length || 0) + 2, chapter_name: '', description: '' });
                setIsTopicModalOpen(false);
            } else {
                console.error('新增章節失敗');
            }
        } catch (err) {
            console.error('新增章節錯誤:', err);
        }
    };



    const handleUnifiedDelete = async (contentId: number) => {
        if (!courseId) return;

        try {
            const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/contents/${contentId}/remove`, {
                method: 'PATCH',
                headers: getAuthHeaders()
            });

            if (response.ok) {
                setToast({ show: true, message: '已從本章節移除', type: 'success' });
                queryClient.invalidateQueries({ queryKey: ['course-contents', courseId] });
            } else {
                throw new Error('刪除失敗');
            }
        } catch (err) {
            console.error(err);
            setToast({ show: true, message: '刪除失敗', type: 'error' });
        } finally {
            setConfirmDialog({ show: false, type: null, id: null });
        }
    };

    const handleNavigateToEdit = (contentId: number, type: string, unitId?: number) => {
        // Navigate to edit page with unit_id and mode=edit to preserve it during update
        const params = new URLSearchParams({ type, mode: 'edit' });
        if (unitId) params.append('unit_id', unitId.toString());
        navigate(`/teacher/courses/${courseId}/content/edit/${contentId}?${params.toString()}`);
    };



    // ==================== Render ====================

    if (isLoading) {
        return (
            <div className="py-12 flex justify-center">
                <Spinner />
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-destructive-light border border-destructive text-destructive px-4 py-3 rounded-lg mx-6 mt-6">
                {error}
            </div>
        );
    }

    if (!course) {
        return (
            <div className="text-center py-12 text-neutral-text-tertiary">
                課程不存在
            </div>
        );
    }

    return (
        <div className="w-full min-h-full bg-transparent relative">
            <div className="relative z-10 p-6 space-y-8">{/* Content */}
                {/* ==================== 備課引導 ==================== */}
                <PrepGuide />

                {/* ==================== 公告區塊 ==================== */}
                <div className="bg-white rounded-xl border border-neutral-border shadow-sm p-4 hover:shadow-md transition-shadow">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-4">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-blue-50 rounded-full">
                                    <FaBell className="text-theme-primary" size={18} />
                                </div>
                                <h2 className="text-lg font-semibold text-neutral-text-main">最新公告</h2>
                            </div>

                            {/* Integrated Course Code Display */}
                            {enrollmentCode && !enrollmentCode.is_expired && (
                                <div
                                    className="flex items-center gap-3 bg-blue-50/50 px-3 py-1.5 rounded-lg border border-blue-100 cursor-pointer hover:bg-blue-100/50 transition-colors"
                                    onClick={() => setIsCodeModalOpen(true)}
                                    title="點擊放大顯示課程碼"
                                >
                                    <div className="flex items-center gap-2">
                                        <RiLinkUnlinkM className="text-blue-500" size={14} />
                                        <span className="text-sm text-slate-600 font-medium">課程碼：</span>
                                        <span className="text-base font-mono font-bold text-slate-700">{enrollmentCode.code}</span>
                                        <span className="text-xs text-slate-400 ml-2">
                                            (有效期限：{new Date(enrollmentCode.expires_at).toLocaleDateString()}，{Math.ceil((new Date(enrollmentCode.expires_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24))} 天後過期)
                                        </span>
                                    </div>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            navigator.clipboard.writeText(enrollmentCode.code);
                                            setToast({ show: true, message: '課程碼已複製', type: 'success' });
                                        }}
                                        className="text-xs text-blue-600 hover:text-blue-800 font-bold hover:underline ml-1"
                                    >
                                        複製
                                    </button>
                                </div>
                            )}
                        </div>

                        <div className="flex items-center gap-2">
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleGenerateEnrollmentCode();
                                }}
                                className="bg-blue-50/50 hover:bg-white flex items-center gap-2 text-sm py-2 px-4 rounded-lg border border-blue-100 shadow-sm hover:shadow-md transition-all group"
                                title={enrollmentCode ? '重新產生課程碼' : '產生課程碼'}
                            >
                                <MdAddLink size={16} className="text-[#0EA5E9]" />
                                <span className="text-[#0EA5E9] font-medium">
                                    {enrollmentCode ? '產生課程碼' : '產生課程碼'}
                                </span>
                            </button>
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    setIsAnnouncementModalOpen(true);
                                }}
                                className="bg-blue-50/50 hover:bg-white flex items-center gap-2 text-sm py-2 px-4 rounded-lg border border-blue-100 shadow-sm hover:shadow-md transition-all group"
                            >
                                <FaPlus size={12} className="text-[#0EA5E9]" />
                                <span className="bg-gradient-to-r from-[#0EA5E9] to-[#14B8A6] bg-clip-text text-transparent font-bold">
                                    新增公告
                                </span>
                            </button>
                        </div>
                    </div>

                    <div className="p-4 border-t border-neutral-border bg-gray-50/30">

                        <div className={`space-y-3 ${expandedAnnouncements.length > 0 ? '' : 'max-h-[220px] overflow-y-auto pr-1'}`}>
                            {announcements.length > 0 ? (
                                announcements.map((announcement) => {
                                    const isExpanded = expandedAnnouncements.includes(announcement.id);
                                    return (
                                        <div
                                            key={announcement.id}
                                            className={`rounded-xl border transition-all duration-200 overflow-hidden ${isExpanded ? 'border-blue-200 shadow-md transform -translate-y-0.5' : 'border-blue-100 hover:border-blue-300 hover:shadow-sm bg-blue-50/30'}`}
                                        >
                                            {/* Announcement header - always visible, clickable */}
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
                                                <div className={`w-2 h-2 mt-2 rounded-full bg-theme-primary flex-shrink-0 transition-transform duration-300 ${isExpanded ? 'scale-125' : ''}`} />

                                                <div className="flex-grow min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        {announcement.is_pinned && (
                                                            <FaThumbtack className="text-theme-primary -rotate-45" size={14} title="已置頂" />
                                                        )}
                                                        <h3 className={`text-base font-medium transition-colors ${isExpanded ? 'text-blue-700 font-bold' : 'text-neutral-text-main'}`}>
                                                            {announcement.title}
                                                        </h3>
                                                        {!announcement.is_visible && (
                                                            <span className="text-[10px] bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded flex items-center gap-1">
                                                                <FaEyeSlash size={10} /> 學生不可見
                                                            </span>
                                                        )}
                                                    </div>

                                                    <span className="text-xs text-neutral-text-tertiary block mt-1">
                                                        {formatDateTime(announcement.created_at)}
                                                    </span>
                                                </div>

                                                {/* Action Buttons */}
                                                <div className="flex items-center gap-1 flex-shrink-0">
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleTogglePin(announcement);
                                                        }}
                                                        className={`p-2 rounded-lg transition-all ${announcement.is_pinned ? 'text-theme-primary bg-blue-50' : 'text-neutral-icon hover:text-theme-primary hover:bg-white/50'}`}
                                                        title={announcement.is_pinned ? "取消置頂" : "置頂公告"}
                                                    >
                                                        <FaThumbtack size={14} className={announcement.is_pinned ? "-rotate-45 transition-transform" : "opacity-40"} />
                                                    </button>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleToggleVisibility(announcement);
                                                        }}
                                                        className={`p-2 rounded-lg transition-all ${!announcement.is_visible ? 'text-orange-500 bg-orange-50' : 'text-neutral-icon hover:text-theme-primary hover:bg-white/50'}`}
                                                        title={announcement.is_visible ? "對學生隱藏" : "對學生顯示"}
                                                    >
                                                        {announcement.is_visible ? <FaEye size={14} /> : <FaEyeSlash size={14} />}
                                                    </button>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleEditAnnouncement(announcement);
                                                        }}
                                                        className="p-2 rounded-lg text-neutral-icon hover:text-theme-primary hover:bg-white/50 transition-all"
                                                        title="編輯公告"
                                                    >
                                                        <FaEdit size={14} />
                                                    </button>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setConfirmDialog({ show: true, type: 'announcement', id: announcement.id });
                                                        }}
                                                        className="p-2 rounded-lg text-neutral-icon hover:text-destructive hover:bg-white/50 transition-all"
                                                        title="刪除公告"
                                                    >
                                                        <FaTrash size={14} />
                                                    </button>
                                                    <div className={`text-neutral-text-tertiary transition-transform duration-300 p-2 ${isExpanded ? 'rotate-180' : ''}`}>
                                                        <FaChevronDown size={12} />
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Announcement content - expandable */}
                                            {isExpanded && (
                                                <div className="bg-white border-t border-blue-100">
                                                    {/* 公告內容 */}
                                                    {announcement.content && (
                                                        <div className="px-5 py-4">
                                                            <div
                                                                className="text-sm text-neutral-text-main announcement-content"
                                                                dangerouslySetInnerHTML={{ __html: announcement.content }}
                                                            />
                                                        </div>
                                                    )}

                                                    {/* 附件列表 */}
                                                    {(announcementAttachments[announcement.id]?.length > 0 || true) && (
                                                        <div className="px-5 pb-4">
                                                            {announcementAttachments[announcement.id]?.length > 0 && (
                                                                <div className="mb-2 pt-2 border-t border-dashed border-gray-100">
                                                                    <h4 className="text-xs font-semibold text-neutral-text-secondary mb-2">附件檔案</h4>
                                                                    <AttachmentList
                                                                        attachments={announcementAttachments[announcement.id]}
                                                                        onDelete={(attachmentId) => handleDeleteAttachment(announcement.id, attachmentId)}
                                                                        canDelete={true}
                                                                        showUploader={false}
                                                                    />
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })
                            ) : (
                                <div className="text-center py-4 text-sm text-neutral-text-tertiary bg-gray-50 rounded-lg border border-gray-100">
                                    本課程尚無公告
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* ==================== 課程設定區塊 (加入代碼) ==================== */}


                {/* ==================== 課程內容標題 ==================== */}
                <div className="px-4 flex items-center justify-between mb-1">
                    <h2 className="text-xl font-bold text-neutral-text-main">課程內容</h2>
                    <button
                        onClick={() => {
                            setNewChapter({ chapter_number: course.units.length + 1, chapter_name: '', description: '' });
                            setIsTopicModalOpen(true);
                        }}
                        className="bg-white hover:bg-blue-50 flex items-center gap-2 text-sm py-2 px-4 rounded-lg border border-blue-100 shadow-sm hover:shadow-md transition-all group"
                    >
                        <FaPlus size={12} className="text-[#0EA5E9]" />
                        <span className="bg-gradient-to-r from-[#0EA5E9] to-[#14B8A6] bg-clip-text text-transparent font-bold">
                            新增章節
                        </span>
                    </button>
                </div>

                {/* ==================== 週次列表 ==================== */}
                {course.units.length === 0 ? (
                    <div className="text-center py-12 text-neutral-text-tertiary bg-white rounded-xl border border-neutral-border">
                        此課程尚未設定章節，請點擊「新增章節」建立第一個單元
                    </div>
                ) : (
                    <div className="space-y-5">
                        {course.units.map((unit) => {
                            const isExpanded = expandedWeeks.includes(unit.topic_id);
                            const currentMatTab = materialTabs[unit.id] || 'preview';
                            const filteredMaterials = unit.materials?.filter(m => {
                                const subtype = m.content_subtype;
                                if (currentMatTab === 'preview') return subtype === 'preview' || !subtype || subtype === 'attachment';
                                return subtype === 'review' || subtype === 'exercise' || subtype === 'summary' || subtype === 'summary_report';
                            }) || [];

                            return (
                                <div
                                    key={unit.id}
                                    id={`unit-card-${unit.topic_id}`}
                                    className="bg-white rounded-xl border border-transparent shadow-[0_4px_20px_rgba(0,0,0,0.05)] hover:shadow-[0_8px_30px_rgba(0,0,0,0.08)] transition-all duration-300"
                                >
                                    {/* 章節標題列 */}
                                    <div
                                        className={`p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50 transition-colors ${isExpanded ? 'rounded-t-xl' : 'rounded-xl'}`}
                                        onClick={() => toggleWeek(unit.topic_id)}
                                        title={isExpanded ? '收合章節' : '展開章節'}
                                    >
                                        <div className="flex items-center gap-3 flex-1 select-none">
                                            <h3 className={`text-lg font-bold transition-colors ${isExpanded ? 'text-blue-700' : 'text-neutral-text-main'}`}>
                                                章節 {unit.topic_id}: {unit.name}
                                            </h3>
                                        </div>

                                        {/* 教師操作按鈕 */}
                                        <div className="flex items-center gap-1">
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    handleEditChapter(unit);
                                                }}
                                                className="p-2 rounded-lg text-neutral-icon hover:text-theme-primary hover:bg-theme-primary-light/20 transition-all"
                                                title="編輯章節"
                                            >
                                                <FaEdit size={14} />
                                            </button>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setConfirmDialog({ show: true, type: 'chapter', id: unit.id });
                                                }}
                                                className="p-2 rounded-lg text-neutral-icon hover:text-destructive hover:bg-red-50 transition-all"
                                                title="刪除章節"
                                            >
                                                <FaTrash size={14} />
                                            </button>
                                            <div className="text-neutral-text-tertiary ml-2">
                                                {isExpanded ? <FaChevronDown className="rotate-180 transition-transform" /> : <FaChevronDown className="transition-transform" />}
                                            </div>
                                        </div>
                                    </div>

                                    {/* 展開的內容區塊 - 雙欄設計 */}
                                    {isExpanded && (
                                        <div className="px-6 pb-6 pt-2 border-t border-neutral-border/50 bg-gray-50/30 rounded-b-xl">
                                            {/* 章節說明 */}
                                            {unit.description && (
                                                <div className="mb-6">
                                                    <div
                                                        className="text-neutral-text-secondary mt-2 text-sm prose prose-sm max-w-none"
                                                        dangerouslySetInnerHTML={{ __html: unit.description }}
                                                    />
                                                </div>
                                            )}

                                            {/* 改為兩欄佈局：教材 + 試卷 */}
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
                                                {/* ==================== Materials Section (教材) ==================== */}
                                                <div className="bg-white rounded-xl border border-neutral-border p-5 shadow-sm hover:shadow-md transition-all duration-200 group flex flex-col h-full">
                                                    <div className="flex items-center justify-between mb-4">
                                                        <div className="flex items-center gap-2">
                                                            <div className="p-2 bg-blue-50 text-theme-primary rounded-lg">
                                                                <FaBook size={16} />
                                                            </div>
                                                            <h4 className="font-bold text-neutral-text-main text-lg">教材</h4>
                                                            <span className="text-xs font-medium bg-gray-100 text-neutral-text-secondary px-2 py-0.5 rounded-full">
                                                                {filteredMaterials.length + (currentMatTab === 'preview' ? (unitAttachments[unit.id]?.length || 0) : 0)}
                                                            </span>
                                                        </div>

                                                        {/* Segmented Control */}
                                                        <div className="flex items-center">
                                                            <button
                                                                onClick={() => setMaterialTabs(prev => ({ ...prev, [unit.id]: 'preview' }))}
                                                                className={`px-4 py-1.5 rounded-full text-sm font-bold flex items-center gap-1.5 transition-all ${currentMatTab === 'preview' ? 'bg-blue-50 text-theme-primary' : 'text-neutral-text-tertiary hover:bg-gray-50'}`}
                                                            >
                                                                <FaBookOpenReader size={12} /> 課前預習
                                                            </button>
                                                            <div className="w-px h-4 bg-gray-200 mx-1.5"></div>
                                                            <button
                                                                onClick={() => setMaterialTabs(prev => ({ ...prev, [unit.id]: 'review' }))}
                                                                className={`px-4 py-1.5 rounded-full text-sm font-bold flex items-center gap-1.5 transition-all ${currentMatTab === 'review' ? 'bg-blue-50 text-theme-primary' : 'text-neutral-text-tertiary hover:bg-gray-50'}`}
                                                            >
                                                                <MdRateReview size={12} /> 課後複習
                                                            </button>
                                                        </div>
                                                    </div>

                                                    <div className="flex items-center gap-2 mb-4">
                                                        <button
                                                            onClick={() => {
                                                                setAddContentTarget({ type: 'material', unitId: unit.id });
                                                                setActiveAddTab('uploaded');
                                                                setIsAddContentModalOpen(true);
                                                            }}
                                                            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm text-theme-primary bg-blue-50 hover:bg-blue-100 rounded-full transition-all font-bold"
                                                        >
                                                            <FaCloudUploadAlt size={14} /> 上傳
                                                        </button>
                                                        <button
                                                            onClick={() => navigate(`/teacher/courses/${courseId}/generate?type=material&unit_id=${unit.id}&subtype=${currentMatTab}`)}
                                                            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-theme-primary text-white hover:bg-theme-primary-hover rounded-full transition-all font-bold"
                                                        >
                                                            <FaMagic size={12} /> AI 生成
                                                        </button>
                                                    </div>

                                                    <div className="space-y-2 flex-grow">
                                                        {filteredMaterials.length === 0 && (currentMatTab !== 'preview' || !unitAttachments[unit.id]?.length) ? (
                                                            <div className="text-center py-6 text-neutral-text-tertiary text-sm italic">
                                                                尚未新增{currentMatTab === 'preview' ? '課前' : '課後'}教材
                                                            </div>
                                                        ) : (
                                                            <>
                                                                {/* Existing Materials */}
                                                                {(() => {
                                                                    let sequentialCounter = 0;
                                                                    return filteredMaterials.map((material, idx) => {
                                                                        const isAttachment = material.content_subtype === 'attachment';
                                                                        if (!isAttachment) {
                                                                            sequentialCounter++;
                                                                        }

                                                                        return (
                                                                            <div
                                                                                key={material.id}
                                                                                className="flex items-center gap-3 p-3 rounded-lg hover:bg-blue-50/50 border border-transparent hover:border-blue-100 transition-all group/item cursor-pointer"
                                                                                onClick={() => handleNavigateToEdit(material.id, 'material', unit.id)}
                                                                            >
                                                                                <div className="flex-grow min-w-0 flex items-center">
                                                                                    <Tooltip content="編輯教材" position="bottom" className="flex-grow min-w-0">
                                                                                        <div className="flex items-center gap-3">
                                                                                            <div className="flex-shrink-0">
                                                                                                {isAttachment ? (
                                                                                                    getFileIcon('file', material.title, 12, "w-6 h-6 rounded-full bg-gray-50 flex items-center justify-center border border-gray-100")
                                                                                                ) : (
                                                                                                    <div className="w-6 h-6 rounded-full bg-blue-50 text-theme-primary flex items-center justify-center text-xs font-bold border border-blue-100">
                                                                                                        {material.display_order || idx + 1}
                                                                                                    </div>
                                                                                                )}
                                                                                            </div>
                                                                                            <div className={`flex-grow min-w-0 ${material.is_visible === false ? 'opacity-50' : ''}`}>
                                                                                                <div className="flex items-center gap-2">
                                                                                                    <div className="text-sm font-medium text-neutral-text-main group-hover/item:text-theme-primary transition-colors truncate">
                                                                                                        {material.title}
                                                                                                    </div>
                                                                                                    {material.is_visible === false && (
                                                                                                        <span className="shrink-0 text-gray-400" title="已隱藏">
                                                                                                            <FaEyeSlash size={12} />
                                                                                                        </span>
                                                                                                    )}
                                                                                                </div>
                                                                                                <div className="text-xs text-neutral-text-tertiary">
                                                                                                    {isAttachment ? '附件' : getSubtypeLabel('material', material.content_subtype)}
                                                                                                </div>
                                                                                            </div>
                                                                                        </div>
                                                                                    </Tooltip>
                                                                                </div>

                                                                                <div className="flex items-center gap-1 opacity-100 md:opacity-0 md:group-hover/item:opacity-100 transition-opacity">
                                                                                    {/* Movement Controls */}
                                                                                    <button
                                                                                        onClick={(e) => { e.stopPropagation(); moveContent(unit.id, 'material', material.content_subtype ?? null, idx, 'up', filteredMaterials); }}
                                                                                        disabled={idx === 0}
                                                                                        className={`p-2 rounded-md hover:bg-gray-100 transition-colors ${idx === 0 ? 'text-gray-300' : 'text-neutral-icon hover:text-theme-primary'}`}
                                                                                        title="上移"
                                                                                    >
                                                                                        <FaArrowUp size={16} />
                                                                                    </button>
                                                                                    <button
                                                                                        onClick={(e) => { e.stopPropagation(); moveContent(unit.id, 'material', material.content_subtype ?? null, idx, 'down', filteredMaterials); }}
                                                                                        disabled={idx === filteredMaterials.length - 1}
                                                                                        className={`p-2 rounded-md hover:bg-gray-100 transition-colors ${idx === filteredMaterials.length - 1 ? 'text-gray-300' : 'text-neutral-icon hover:text-theme-primary'}`}
                                                                                        title="下移"
                                                                                    >
                                                                                        <FaArrowDown size={16} />
                                                                                    </button>
                                                                                    <Tooltip content="刪除" position="left">
                                                                                        <button
                                                                                            onClick={(e) => {
                                                                                                e.stopPropagation(); // Prevent triggering row click (edit)
                                                                                                setConfirmDialog({ show: true, type: 'content', id: material.id });
                                                                                            }}
                                                                                            className="p-2 text-neutral-icon hover:text-destructive hover:bg-red-50 rounded-md transition-colors"
                                                                                        >
                                                                                            <FaTrash size={16} />
                                                                                        </button>
                                                                                    </Tooltip>
                                                                                </div>
                                                                            </div>
                                                                        );
                                                                    });
                                                                })()}

                                                                {/* 附件列表 (只在預習分頁顯示) */}
                                                                {currentMatTab === 'preview' && unitAttachments[unit.id]?.map((attachment) => (
                                                                    <div
                                                                        key={`attachment-${attachment.id}`}
                                                                        className="flex items-center gap-3 p-3 rounded-lg hover:bg-blue-50/50 border border-transparent hover:border-blue-100 transition-all group/item cursor-pointer"
                                                                        onClick={() => {
                                                                            const link = document.createElement('a');
                                                                            link.href = `${API_BASE_URL}${attachment.download_url}`;
                                                                            link.download = attachment.original_file_name;
                                                                            document.body.appendChild(link);
                                                                            link.click();
                                                                            document.body.removeChild(link);
                                                                        }}
                                                                    >
                                                                        <div className="flex-grow min-w-0 flex items-center">
                                                                            <Tooltip content="點擊下載附件" position="bottom" className="flex-grow min-w-0">
                                                                                <div className="flex items-center gap-3">
                                                                                    <div className="flex-shrink-0">
                                                                                        {getFileIcon(attachment.file_type, attachment.original_file_name)}
                                                                                    </div>
                                                                                    <div className="flex-grow min-w-0">
                                                                                        <div className="text-sm font-medium text-neutral-text-main group-hover/item:text-theme-primary transition-colors truncate">
                                                                                            {attachment.original_file_name}
                                                                                        </div>
                                                                                        <div className="text-xs text-neutral-text-tertiary">
                                                                                            單元附件
                                                                                        </div>
                                                                                    </div>
                                                                                </div>
                                                                            </Tooltip>
                                                                        </div>

                                                                        <div className="flex items-center gap-1 opacity-100 md:opacity-0 md:group-hover/item:opacity-100 transition-opacity">
                                                                            <Tooltip content="刪除" position="left">
                                                                                <button
                                                                                    onClick={(e) => {
                                                                                        e.stopPropagation();
                                                                                        handleDeleteUnitAttachment(unit.id, attachment.id);
                                                                                    }}
                                                                                    className="p-2 text-neutral-icon hover:text-destructive hover:bg-red-50 rounded-md transition-colors"
                                                                                >
                                                                                    <FaTrash size={16} />
                                                                                </button>
                                                                            </Tooltip>
                                                                        </div>
                                                                    </div>
                                                                ))}
                                                            </>
                                                        )}
                                                    </div>
                                                </div>

                                                {/* ==================== Papers Section (試卷) ==================== */}
                                                {(() => {
                                                    const currentPaperTab = paperTabs[unit.id] || 'homework';
                                                    const filteredExams = unit.exams?.filter(exam => {
                                                        if (currentPaperTab === 'homework') return exam.content_subtype === 'homework';
                                                        return !exam.content_subtype || ['quiz', 'midterm', 'final', 'exam'].includes(exam.content_subtype);
                                                    }) || [];

                                                    return (
                                                        <div className="bg-white rounded-xl border border-neutral-border p-5 shadow-sm hover:shadow-md transition-all duration-200 group flex flex-col h-full">
                                                            <div className="flex items-center justify-between mb-4">
                                                                <div className="flex items-center gap-2">
                                                                    <div className="p-2 bg-blue-50 text-theme-primary rounded-lg">
                                                                        <FaListOl size={16} />
                                                                    </div>
                                                                    <h4 className="font-bold text-neutral-text-main text-lg">試卷</h4>
                                                                    <span className="text-xs font-medium bg-gray-100 text-neutral-text-secondary px-2 py-0.5 rounded-full">
                                                                        {filteredExams.length}
                                                                    </span>
                                                                </div>

                                                                {/* Segmented Control */}
                                                                <div className="flex items-center">
                                                                    <button
                                                                        onClick={() => setPaperTabs(prev => ({ ...prev, [unit.id]: 'homework' }))}
                                                                        className={`px-4 py-1.5 rounded-full text-sm font-bold flex items-center gap-1.5 transition-all ${currentPaperTab === 'homework' ? 'bg-blue-50 text-theme-primary' : 'text-neutral-text-tertiary hover:bg-gray-50'}`}
                                                                    >
                                                                        <FaEdit size={12} /> 作業
                                                                    </button>
                                                                    <div className="w-px h-4 bg-gray-200 mx-1.5"></div>
                                                                    <button
                                                                        onClick={() => setPaperTabs(prev => ({ ...prev, [unit.id]: 'exam' }))}
                                                                        className={`px-4 py-1.5 rounded-full text-sm font-bold flex items-center gap-1.5 transition-all ${currentPaperTab === 'exam' ? 'bg-blue-50 text-theme-primary' : 'text-neutral-text-tertiary hover:bg-gray-50'}`}
                                                                    >
                                                                        <FaClipboardCheck size={12} /> 考試
                                                                    </button>
                                                                </div>
                                                            </div>

                                                            <div className="flex items-center gap-2 mb-4">
                                                                <button
                                                                    onClick={() => {
                                                                        setAddContentTarget({ type: 'exam', unitId: unit.id });
                                                                        setActiveAddTab('generated');
                                                                        setIsAddContentModalOpen(true);
                                                                    }}
                                                                    className="flex flex-1 items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 text-neutral-text-main rounded-full transition-all font-bold whitespace-nowrap"
                                                                >
                                                                    <FaHistory size={12} /> 從歷史紀錄加入
                                                                </button>
                                                                <button
                                                                    onClick={() => {
                                                                        const params = new URLSearchParams({
                                                                            type: 'exam',
                                                                            unit_id: unit.id.toString(),
                                                                            mode: 'manual',
                                                                            subtype: currentPaperTab === 'exam' ? 'quiz' : 'homework'
                                                                        });
                                                                        navigate(`/teacher/courses/${courseId}/content/new?${params.toString()}`);
                                                                    }}
                                                                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm text-theme-primary bg-blue-50 hover:bg-blue-100 rounded-full transition-all font-bold"
                                                                >
                                                                    <FaPlus size={12} /> 新增
                                                                </button>
                                                                <button
                                                                    onClick={() => {
                                                                        const params = new URLSearchParams({
                                                                            type: 'exam',
                                                                            unit_id: unit.id.toString(),
                                                                            subtype: currentPaperTab === 'exam' ? 'quiz' : 'homework'
                                                                        });
                                                                        navigate(`/teacher/courses/${courseId}/generate?${params.toString()}`);
                                                                    }}
                                                                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-theme-primary text-white hover:bg-theme-primary-hover rounded-full transition-all font-bold"
                                                                >
                                                                    <FaMagic size={12} /> AI 生成
                                                                </button>
                                                            </div>

                                                            <div className="space-y-2 flex-grow">
                                                                {filteredExams.length === 0 ? (
                                                                    <div className="text-center py-6 text-neutral-text-tertiary text-sm italic">
                                                                        尚未新增{currentPaperTab === 'homework' ? '作業' : '考試'}
                                                                    </div>
                                                                ) : (
                                                                    <>
                                                                        {filteredExams.map((exam, idx) => (
                                                                            <div
                                                                                key={`exam-${exam.id}`}
                                                                                className="flex items-center gap-3 p-3 rounded-lg hover:bg-blue-50/50 border border-transparent hover:border-blue-100 transition-all group/item cursor-pointer"
                                                                                onClick={() => handleNavigateToEdit(exam.id, 'exam', unit.id)}
                                                                            >
                                                                                <div className="flex-grow min-w-0 flex items-center">
                                                                                    <Tooltip content="編輯試卷" position="bottom" className="flex-grow min-w-0">
                                                                                        <div className="flex items-center gap-3">
                                                                                            <div className="p-1.5 rounded-md bg-blue-50 text-theme-primary flex items-center justify-center">
                                                                                                {exam.content_subtype === 'homework' ? <FaEdit size={14} /> : <FaClipboardCheck size={14} />}
                                                                                            </div>
                                                                                            <div className={`flex-grow min-w-0 ${exam.is_visible === false ? 'opacity-50' : ''}`}>
                                                                                                <div className="flex items-center gap-2">
                                                                                                    <div className="text-sm font-medium text-neutral-text-main group-hover/item:text-theme-primary transition-colors truncate">
                                                                                                        {exam.title}
                                                                                                    </div>
                                                                                                    {exam.is_visible === false && (
                                                                                                        <span className="shrink-0 text-gray-400" title="已隱藏">
                                                                                                            <FaEyeSlash size={12} />
                                                                                                        </span>
                                                                                                    )}
                                                                                                </div>
                                                                                                <div className="text-xs text-neutral-text-tertiary">
                                                                                                    {getSubtypeLabel('exam', exam.content_subtype)}
                                                                                                </div>
                                                                                            </div>
                                                                                        </div>
                                                                                    </Tooltip>
                                                                                </div>

                                                                                <div className="flex items-center gap-1 opacity-100 md:opacity-0 md:group-hover/item:opacity-100 transition-opacity">
                                                                                    {/* Movement Controls */}
                                                                                    <button
                                                                                        onClick={(e) => { e.stopPropagation(); moveContent(unit.id, 'exam', exam.content_subtype ?? null, idx, 'up', filteredExams); }}
                                                                                        disabled={idx === 0}
                                                                                        className={`p-2 rounded-md hover:bg-gray-100 transition-colors ${idx === 0 ? 'text-gray-300' : 'text-neutral-icon hover:text-theme-primary'}`}
                                                                                        title="上移"
                                                                                    >
                                                                                        <FaArrowUp size={16} />
                                                                                    </button>
                                                                                    <button
                                                                                        onClick={(e) => { e.stopPropagation(); moveContent(unit.id, 'exam', exam.content_subtype ?? null, idx, 'down', filteredExams); }}
                                                                                        disabled={idx === filteredExams.length - 1}
                                                                                        className={`p-2 rounded-md hover:bg-gray-100 transition-colors ${idx === filteredExams.length - 1 ? 'text-gray-300' : 'text-neutral-icon hover:text-theme-primary'}`}
                                                                                        title="下移"
                                                                                    >
                                                                                        <FaArrowDown size={16} />
                                                                                    </button>
                                                                                    <Tooltip content="刪除" position="left">
                                                                                        <button
                                                                                            onClick={(e) => {
                                                                                                e.stopPropagation();
                                                                                                setConfirmDialog({ show: true, type: 'content', id: exam.id });
                                                                                            }}
                                                                                            className="p-2 text-neutral-icon hover:text-destructive hover:bg-red-50 rounded-md transition-colors"
                                                                                        >
                                                                                            <FaTrash size={16} />
                                                                                        </button>
                                                                                    </Tooltip>
                                                                                </div>
                                                                            </div>
                                                                        ))}
                                                                    </>
                                                                )}
                                                            </div>
                                                        </div>
                                                    );
                                                })()}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* ==================== Modals ==================== */}

                {/* 新增公告 Modal */}
                <WideModal
                    isOpen={isAnnouncementModalOpen}
                    onClose={() => setIsAnnouncementModalOpen(false)}
                    title="新增公告"
                >
                    <div className="space-y-4 pt-6">
                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-1">標題</label>
                            <input
                                type="text"
                                value={newAnnouncement.title}
                                onChange={(e) => setNewAnnouncement({ ...newAnnouncement, title: e.target.value })}
                                className="w-full px-4 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-theme-ring focus:border-theme-primary"
                                placeholder="請輸入公告標題"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-1">說明 <span className="text-neutral-text-tertiary"></span></label>
                            <RichTextEditor
                                value={newAnnouncement.content}
                                onChange={(value) => setNewAnnouncement({ ...newAnnouncement, content: value })}
                                placeholder="請輸入公告內容..."
                            />
                        </div>

                        {/* Attachments Section */}
                        <div className="border-t pt-4">
                            <label className="block text-sm font-medium text-neutral-text-main mb-2">附件</label>
                            {pendingAnnouncementAttachments.length > 0 && (
                                <div className="space-y-2 mb-3">
                                    {pendingAnnouncementAttachments.map((file, index) => (
                                        <div key={index} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg border border-neutral-border">
                                            <div className="flex items-center gap-2">
                                                <FaFileAlt className="text-theme-primary" size={16} />
                                                <span className="text-sm text-neutral-text-main">{file.name}</span>
                                                <span className="text-xs text-neutral-text-secondary">
                                                    {(file.size / 1024 / 1024).toFixed(2)} MB
                                                </span>
                                            </div>
                                            <button
                                                onClick={() => setPendingAnnouncementAttachments(prev => prev.filter((_, i) => i !== index))}
                                                className="p-1 rounded text-neutral-icon hover:text-destructive hover:bg-red-50"
                                                title="移除附件"
                                            >
                                                <FaTrash size={12} />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                            <AttachmentUpload
                                onUpload={async (file) => {
                                    setPendingAnnouncementAttachments(prev => [...prev, file]);
                                }}
                            />
                        </div>

                        {!newAnnouncement.title.trim() && (
                            <p className="text-sm text-orange-600">請輸入標題，才能新增公告</p>
                        )}
                        <div className="flex justify-end gap-3 pt-2">
                            <Button variant="secondary" onClick={() => setIsAnnouncementModalOpen(false)} idleText="取消" />
                            <Button
                                variant="primary"
                                onClick={handleAddAnnouncement}
                                idleText="新增"
                                disabled={!newAnnouncement.title.trim()}
                            />
                        </div>
                    </div>
                </WideModal>

                {/* 新增章節 Modal */}
                <WideModal
                    isOpen={isTopicModalOpen}
                    onClose={() => setIsTopicModalOpen(false)}
                    title="新增章節"
                >
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-1">章節編號</label>
                            <input
                                type="number"
                                min="1"
                                value={newChapter.chapter_number}
                                onChange={(e) => setNewChapter({ ...newChapter, chapter_number: parseInt(e.target.value) || 1 })}
                                className="w-full px-4 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-theme-ring focus:border-theme-primary"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-1">章節名稱</label>
                            <input
                                type="text"
                                value={newChapter.chapter_name}
                                onChange={(e) => setNewChapter({ ...newChapter, chapter_name: e.target.value })}
                                className="w-full px-4 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-theme-ring focus:border-theme-primary"
                                placeholder="例如：機器學習-監督式學習演算法"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-1">章節說明</label>
                            <RichTextEditor
                                value={newChapter.description}
                                onChange={(value) => setNewChapter({ ...newChapter, description: value })}
                                placeholder="輸入學習知識點或章節說明..."
                            />
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-2">教材</label>

                            {/* 待上傳教材 */}
                            {pendingUnitAttachments.length > 0 && (
                                <div className="mb-3 space-y-2">
                                    <p className="text-xs text-neutral-text-secondary">待上傳教材：</p>
                                    {pendingUnitAttachments.map((file, index) => (
                                        <div key={index} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg border border-neutral-border">
                                            <div className="flex items-center gap-2">
                                                <FaFileAlt className="text-theme-primary" size={16} />
                                                <span className="text-sm text-neutral-text-main">{file.name}</span>
                                                <span className="text-xs text-neutral-text-secondary">
                                                    ({(file.size / 1024 / 1024).toFixed(2)} MB)
                                                </span>
                                            </div>
                                            <button
                                                onClick={() => setPendingUnitAttachments(prev => prev.filter((_, i) => i !== index))}
                                                className="p-1 rounded text-neutral-icon hover:text-destructive hover:bg-red-50"
                                                title="移除附件"
                                            >
                                                <FaTrash size={12} />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}

                            <AttachmentUpload
                                onUpload={async (file) => {
                                    setPendingUnitAttachments(prev => [...prev, file]);
                                }}
                            />
                        </div>

                        {!newChapter.chapter_name.trim() && (
                            <p className="text-sm text-orange-600 mt-2">請輸入章節名稱，才能新增章節</p>
                        )}
                        <div className="flex justify-end gap-3 pt-2">
                            <Button variant="secondary" onClick={() => setIsTopicModalOpen(false)} idleText="取消" />
                            <Button
                                variant="primary"
                                onClick={handleAddChapter}
                                idleText="新增"
                                disabled={!newChapter.chapter_name.trim()}
                            />
                        </div>
                    </div>
                </WideModal>

                {/* 編輯章節 Modal */}
                <WideModal
                    isOpen={isEditChapterModalOpen}
                    onClose={() => setIsEditChapterModalOpen(false)}
                    title="編輯章節"
                >
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-1">章節編號</label>
                            <input
                                type="number"
                                min="1"
                                value={newChapter.chapter_number}
                                onChange={(e) => setNewChapter({ ...newChapter, chapter_number: parseInt(e.target.value) || 1 })}
                                className="w-full px-4 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-theme-ring focus:border-theme-primary"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-1">章節名稱</label>
                            <input
                                type="text"
                                value={newChapter.chapter_name}
                                onChange={(e) => setNewChapter({ ...newChapter, chapter_name: e.target.value })}
                                className="w-full px-4 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-theme-ring focus:border-theme-primary"
                                placeholder="例如：機器學習-監督式學習演算法"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-1">章節說明</label>
                            <RichTextEditor
                                value={newChapter.description}
                                onChange={(value) => setNewChapter({ ...newChapter, description: value })}
                                placeholder="輸入學習知識點或章節說明..."
                            />
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-2">教材</label>

                            {/* 現有教材 */}
                            {editingChapter && unitAttachments[editingChapter.id]?.length > 0 && (
                                <div className="mb-3">
                                    <AttachmentList
                                        attachments={unitAttachments[editingChapter.id]}
                                        onDelete={(attachmentId) => handleDeleteUnitAttachment(editingChapter.id, attachmentId)}
                                        canDelete={true}
                                    />
                                </div>
                            )}

                            {/* 待上傳教材 */}
                            {pendingUnitAttachments.length > 0 && (
                                <div className="mb-3 space-y-2">
                                    <p className="text-xs text-neutral-text-secondary">待上傳教材：</p>
                                    {pendingUnitAttachments.map((file, index) => (
                                        <div key={index} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg border border-neutral-border">
                                            <div className="flex items-center gap-2">
                                                <FaFileAlt className="text-theme-primary" size={16} />
                                                <span className="text-sm text-neutral-text-main">{file.name}</span>
                                                <span className="text-xs text-neutral-text-secondary">
                                                    ({(file.size / 1024 / 1024).toFixed(2)} MB)
                                                </span>
                                            </div>
                                            <button
                                                onClick={() => setPendingUnitAttachments(prev => prev.filter((_, i) => i !== index))}
                                                className="p-1 rounded text-neutral-icon hover:text-destructive hover:bg-red-50"
                                                title="移除附件"
                                            >
                                                <FaTrash size={12} />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}

                            <AttachmentUpload
                                onUpload={async (file) => {
                                    setPendingUnitAttachments(prev => [...prev, file]);
                                }}
                                allowedExtensions={['.pdf', '.ppt', '.pptx', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar', '.7z', '.jpg', '.jpeg', '.png', '.gif', '.txt']}
                                maxSizeMB={20}
                            />
                        </div>
                        <div className="flex justify-end gap-3 pt-2">
                            <Button variant="secondary" onClick={() => setIsEditChapterModalOpen(false)} idleText="取消" />
                            <Button
                                variant="primary"
                                onClick={handleUpdateChapter}
                                idleText="儲存"
                                loadingText="儲存中..."
                                successText="已儲存"
                                errorText="儲存失敗"
                                disabled={!newChapter.chapter_name.trim()}
                            />
                        </div>
                    </div>
                </WideModal>

                {/* 新增教材 Modal */}
                <MaterialSelectionModal
                    isOpen={isAddContentModalOpen}
                    title={addContentTarget?.type === 'material' ? '上傳教材' : '新增內容'}
                    onClose={() => {
                        setIsAddContentModalOpen(false);
                        setPendingUnitAttachments([]);
                        setSelectedReferenceIds([]);
                    }}
                    activeTab={activeAddTab}
                    onTabChange={setActiveAddTab}
                    hideUploadedTab={addContentTarget?.type !== 'material'}
                    materials={referenceMaterials || []}
                    generatedMaterials={(allGeneratedMaterials || []).filter(c => {
                        if (addContentTarget?.type === 'material') {
                            // Map 'summary_report' and 'summary' to 'material' for filtering
                            return c.content_type === 'material' || c.content_type === 'summary_report' || c.content_type === 'summary';
                        }
                        const ctype = (c.content_type || '').toLowerCase();
                        return ctype.includes('exam') || ctype.includes('quiz') || ctype.includes('test');
                    })}
                    courseUnits={courseData?.units || []}
                    isLoading={isGeneratedLoading}
                    isFetching={isGeneratedFetching}
                    selectedKeys={new Set(selectedReferenceIds.map(id => `uploaded:${id}`))}
                    onSelectionChange={(keys) => {
                        const ids = Array.from(keys)
                            .filter(key => key.startsWith('uploaded:'))
                            .map(key => parseInt(key.split(':')[1]));
                        setSelectedReferenceIds(ids);
                    }}
                    isUploading={isUploading}
                    onUploadFile={async (file) => {
                        if (!addContentTarget?.unitId) return;
                        setIsUploading(true);
                        setToast({ show: true, message: '開始上傳...', type: 'info' });
                        const startTime = Date.now();

                        try {
                            const formData = new FormData();
                            formData.append('file', file);
                            formData.append('course_id', courseId || '0');

                            const data = await authClient.postFormData('/api/v1/ingest', formData) as { unique_content_id?: number };

                            const duration = Date.now() - startTime;
                            if (duration < 1000) {
                                await new Promise(resolve => setTimeout(resolve, 1000 - duration));
                            }

                            if (data && data.unique_content_id) {
                                // Attach to unit automatically
                                await fetch(`${API_BASE_URL}/api/v1/materials/${data.unique_content_id}/attach_to_unit/${addContentTarget.unitId}`, {
                                    method: 'POST',
                                    headers: getAuthHeaders()
                                });
                                setToast({ show: true, message: '檔案上傳並加入成功', type: 'success' });
                                queryClient.invalidateQueries({ queryKey: ['course', courseId] });
                                queryClient.invalidateQueries({ queryKey: ['materials', courseId] });

                                // Auto-select the newly uploaded file in the modal
                                setSelectedReferenceIds(prev => [...prev, data.unique_content_id!]);
                            } else {
                                setToast({ show: true, message: '上傳處理中', type: 'info' });
                            }
                        } catch (error) {
                            console.error('上傳失敗:', error);
                            setToast({ show: true, message: `上傳發生錯誤: ${file.name}`, type: 'error' });
                        } finally {
                            setIsUploading(false);
                        }
                    }}
                    onUploadUrl={async (url) => {
                        if (!url.trim() || !addContentTarget?.unitId) return;
                        setIsUploading(true);
                        setToast({ show: true, message: '正在處理連結...', type: 'info' });
                        const startTime = Date.now();

                        try {
                            const formData = new FormData();
                            formData.append('url', url);
                            formData.append('course_id', courseId || '0');

                            const data = await authClient.postFormData('/api/v1/ingest', formData) as { unique_content_id?: number };

                            const duration = Date.now() - startTime;
                            if (duration < 1000) {
                                await new Promise(resolve => setTimeout(resolve, 1000 - duration));
                            }

                            if (data && data.unique_content_id) {
                                // Attach to unit automatically
                                await fetch(`${API_BASE_URL}/api/v1/materials/${data.unique_content_id}/attach_to_unit/${addContentTarget.unitId}`, {
                                    method: 'POST',
                                    headers: getAuthHeaders()
                                });
                                setToast({ show: true, message: '連結處理成功', type: 'success' });
                                queryClient.invalidateQueries({ queryKey: ['course', courseId] });
                                queryClient.invalidateQueries({ queryKey: ['materials', courseId] });

                                // Auto-select the newly added URL in the modal
                                setSelectedReferenceIds(prev => [...prev, data.unique_content_id!]);
                            } else {
                                setToast({ show: true, message: '已提交網址處理請求', type: 'info' });
                            }
                        } catch (error) {
                            console.error("URL Upload error:", error);
                            setToast({ show: true, message: '連結處理錯誤', type: 'error' });
                        } finally {
                            setIsUploading(false);
                        }
                    }}
                    // Directly navigate in 'add' mode
                    onGeneratedClick={(content) => {
                        if (!addContentTarget) return;

                        // Map internal type/subtype to UI-recognized subtype based on context
                        let subtype = content.content_subtype || content.content_type;
                        if (addContentTarget.type === 'material') {
                            const currentTab = materialTabs[addContentTarget.unitId] || 'preview';
                            // If coming from history, generic types should adopt the current tab's subtype
                            if (subtype === 'summary_report' || subtype === 'summary' || subtype === 'material' || !subtype) {
                                subtype = currentTab;
                            }
                        } else if (addContentTarget.type === 'exam') {
                            const currentTab = paperTabs[addContentTarget.unitId] || 'homework';
                            // Map generic 'exam' or missing subtype to specific UI subtype
                            if (subtype === 'exam' || !subtype) {
                                subtype = currentTab === 'exam' ? 'quiz' : 'homework';
                            }
                        }

                        const params = new URLSearchParams({
                            type: addContentTarget.type, // 'material' or 'exam'
                            subtype: subtype || '',
                            mode: 'add',
                            unit_id: addContentTarget.unitId.toString()
                        });
                        navigate(`/teacher/courses/${courseId}/content/edit/${content.id}?${params.toString()}`);
                        setIsAddContentModalOpen(false);
                    }}
                    existingContents={(course?.units?.find((u: any) => u.id === addContentTarget?.unitId)?.materials || [])
                        .concat(course?.units?.find((u: any) => u.id === addContentTarget?.unitId)?.exams || [])}
                    confirmText="加入選中的教材"
                    isConfirmLoading={isUploading}
                    onConfirm={async () => {
                        if (!addContentTarget?.unitId || selectedReferenceIds.length === 0) return;
                        setIsUploading(true);
                        setToast({ show: true, message: '正在加入教材...', type: 'info' });
                        const startTime = Date.now();
                        try {
                            let successCount = 0;
                            for (const uniqueContentId of selectedReferenceIds) {
                                const response = await fetch(`${API_BASE_URL}/api/v1/materials/${uniqueContentId}/attach_to_unit/${addContentTarget.unitId}`, {
                                    method: 'POST',
                                    headers: getAuthHeaders()
                                });

                                if (response.ok) {
                                    successCount++;
                                }
                            }

                            const duration = Date.now() - startTime;
                            if (duration < 600) {
                                await new Promise(resolve => setTimeout(resolve, 600 - duration));
                            }

                            setToast({ show: true, message: `成功加入 ${successCount} 個教材`, type: 'success' });
                            queryClient.invalidateQueries({ queryKey: ['course', courseId] });
                            setSelectedReferenceIds([]);
                            setIsAddContentModalOpen(false);
                        } catch (error) {
                            console.error('批量加入失敗:', error);
                            setToast({ show: true, message: '加入過程發生錯誤', type: 'error' });
                        } finally {
                            setIsUploading(false);
                        }
                    }}
                />

                {/* 編輯公告 Modal */}
                <WideModal
                    isOpen={isEditAnnouncementModalOpen}
                    onClose={() => {
                        setIsEditAnnouncementModalOpen(false);
                        setEditingAnnouncement(null);
                        setNewAnnouncement({ title: '', content: '' });
                    }}
                    title="編輯公告"
                >
                    <div className="space-y-4 pt-6">
                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-1">標題</label>
                            <input
                                type="text"
                                value={newAnnouncement.title}
                                onChange={(e) => setNewAnnouncement({ ...newAnnouncement, title: e.target.value })}
                                className="w-full px-4 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-theme-ring focus:border-theme-primary"
                                placeholder="請輸入公告標題"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-neutral-text-main mb-1">說明</label>
                            <RichTextEditor
                                value={newAnnouncement.content}
                                onChange={(value) => setNewAnnouncement({ ...newAnnouncement, content: value })}
                                placeholder="請輸入公告內容..."
                            />
                        </div>

                        {/* 附件管理 */}
                        {editingAnnouncement && (
                            <div className="mt-6 border-t pt-4">
                                <label className="block text-sm font-medium text-neutral-text-main mb-2">附件</label>

                                {/* 現有附件 */}
                                {announcementAttachments[editingAnnouncement.id]?.length > 0 && (
                                    <div className="mb-3">
                                        <AttachmentList
                                            attachments={announcementAttachments[editingAnnouncement.id] || []}
                                            onDelete={(attachmentId) => handleDeleteAttachment(editingAnnouncement.id, attachmentId)}
                                            canDelete={true}
                                            showUploader={false}
                                        />
                                    </div>
                                )}

                                {/* 待上傳附件 */}
                                {pendingAnnouncementAttachments.length > 0 && (
                                    <div className="mb-3 space-y-2">
                                        <p className="text-xs text-neutral-text-secondary">待上傳附件：</p>
                                        {pendingAnnouncementAttachments.map((file, index) => (
                                            <div key={index} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg border border-neutral-border">
                                                <div className="flex items-center gap-2">
                                                    <FaFileAlt className="text-theme-primary" size={16} />
                                                    <span className="text-sm text-neutral-text-main">{file.name}</span>
                                                    <span className="text-xs text-neutral-text-secondary">
                                                        ({(file.size / 1024 / 1024).toFixed(2)} MB)
                                                    </span>
                                                </div>
                                                <button
                                                    onClick={() => setPendingAnnouncementAttachments(prev => prev.filter((_, i) => i !== index))}
                                                    className="p-1 rounded text-neutral-icon hover:text-destructive hover:bg-red-50"
                                                    title="移除附件"
                                                >
                                                    <FaTrash size={12} />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* 附件上傳 */}
                                <AttachmentUpload
                                    onUpload={async (file) => {
                                        setPendingAnnouncementAttachments(prev => [...prev, file]);
                                    }}
                                />
                            </div>
                        )}

                        <div className="flex justify-end gap-3 pt-6 border-t">
                            <Button
                                variant="secondary"
                                onClick={() => {
                                    setIsEditAnnouncementModalOpen(false);
                                    setEditingAnnouncement(null);
                                    setNewAnnouncement({ title: '', content: '' });
                                }}
                                idleText="取消"
                            />
                            <Button
                                variant="primary"
                                onClick={handleUpdateAnnouncement}
                                idleText="儲存"
                                loadingText="儲存中..."
                                successText="已儲存"
                                errorText="儲存失敗"
                                disabled={!newAnnouncement.title.trim()}
                            />
                        </div>
                        {!newAnnouncement.title.trim() && (
                            <p className="text-sm text-orange-600 mt-2 text-right">請輸入標題才能儲存</p>
                        )}
                    </div>
                </WideModal>

                {/* Toast 通知 */}
                {toast.show && (
                    <Toast
                        key={`${toast.message}-${toast.type}`}
                        message={toast.message}
                        type={toast.type}
                        onClose={() => setToast({ ...toast, show: false })}
                    />
                )}

                {/* 確認刪除對話框 */}
                <ConfirmDialog
                    isOpen={confirmDialog.show}
                    title={
                        confirmDialog.type === 'announcement'
                            ? '刪除公告'
                            : confirmDialog.type === 'content'
                                ? '從章節移除'
                                : confirmDialog.type === 'attachment' || confirmDialog.type === 'unit_attachment'
                                    ? '刪除附件'
                                    : '刪除章節'
                    }
                    message={
                        confirmDialog.type === 'announcement'
                            ? '確定要刪除此公告嗎？此操作無法復原。'
                            : confirmDialog.type === 'content'
                                ? '確定要將此內容從章節中移除嗎？內容會保留在「歷史生成紀錄」中，之後可重新加入。'
                                : confirmDialog.type === 'attachment' || confirmDialog.type === 'unit_attachment'
                                    ? '確定要刪除此附件嗎？對應此附件的學生閱讀紀錄也將被一併刪除，且無法復原，請謹慎思考後再執行刪除。'
                                    : '確定要刪除此章節嗎？此操作無法復原，章節內的所有教材和作業都將被刪除。'
                    }
                    confirmText={confirmDialog.type === 'content' ? '移除' : '刪除'}
                    cancelText="取消"
                    variant="danger"
                    onConfirm={() => {
                        if (confirmDialog.type === 'announcement' && confirmDialog.id) {
                            handleDeleteAnnouncement(confirmDialog.id);
                        } else if (confirmDialog.type === 'chapter' && confirmDialog.id) {
                            handleDeleteChapter(confirmDialog.id);
                        } else if (confirmDialog.type === 'content' && confirmDialog.id) {
                            handleUnifiedDelete(confirmDialog.id);
                        } else if (confirmDialog.type === 'attachment' && confirmDialog.id && confirmDialog.parentId) {
                            executeDeleteAttachment(confirmDialog.parentId, confirmDialog.id);
                        } else if (confirmDialog.type === 'unit_attachment' && confirmDialog.id && confirmDialog.parentId) {
                            executeDeleteUnitAttachment(confirmDialog.parentId, confirmDialog.id);
                        }
                        setConfirmDialog({ show: false, type: null, id: null });
                    }}
                    onCancel={() => setConfirmDialog({ show: false, type: null, id: null })}
                />
            </div>

            {/* Course Code Modal */}
            <Modal
                isOpen={isCodeModalOpen}
                onClose={() => setIsCodeModalOpen(false)}
                title="課程代碼"
                maxWidth="max-w-md"
            >
                <div className="flex flex-col items-center justify-center py-6 space-y-6">
                    <div className="text-center space-y-2">
                        <p className="text-neutral-text-secondary text-sm">請將此代碼分享給學生以加入課程</p>
                    </div>

                    <div className="bg-gray-50 px-8 py-4 rounded-xl border-2 border-dashed border-blue-200">
                        <span className="text-5xl font-mono font-bold text-theme-primary tracking-wider">
                            {enrollmentCode?.code}
                        </span>
                    </div>

                    <div className="flex flex-col items-center gap-2 w-full">
                        <Button
                            variant="primary"
                            onClick={() => {
                                if (enrollmentCode?.code) {
                                    navigator.clipboard.writeText(enrollmentCode.code);
                                    setToast({ show: true, message: '課程碼已複製', type: 'success' });
                                }
                            }}
                            className="w-full justify-center py-3 text-lg"
                            idleText={
                                <div className="flex items-center">
                                    <AiFillCopy className="mr-2" />
                                    <span>複製課程碼</span>
                                </div>
                            }
                        />

                        {enrollmentCode?.expires_at && (
                            <p className="text-xs text-neutral-text-tertiary mt-2">
                                有效期限：{formatDateTime(enrollmentCode.expires_at)}
                            </p>
                        )}
                    </div>
                </div>
            </Modal>

            {/* File Submissions Modal */}
            <WideModal
                isOpen={fileSubmissionsModal.show}
                onClose={() => setFileSubmissionsModal({ show: false, contentId: null, contentTitle: '' })}
                title="檔案繳交管理"
            >
                {fileSubmissionsModal.contentId && (
                    <FileSubmissionsPanel
                        contentId={fileSubmissionsModal.contentId}
                        contentTitle={fileSubmissionsModal.contentTitle}
                    />
                )}
            </WideModal>
        </div>
    );
}

export default Courses;
