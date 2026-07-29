import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiRefreshCw, FiCheck, FiX, FiFileText, FiUser, FiMail, FiCalendar, FiSearch, FiTarget, FiTrash2, FiShield, FiZap, FiEye, FiUsers, FiMessageSquare, FiChevronLeft, FiChevronRight, FiInfo, FiCpu, FiStar, FiActivity, FiBarChart2 } from 'react-icons/fi';
import { BsClipboardDataFill } from 'react-icons/bs';
import { GiArchiveResearch, GiTwoCoins } from 'react-icons/gi';
import { AiTwotoneExperiment } from 'react-icons/ai';
import { FaBook, FaStar } from 'react-icons/fa';
import { MdOutlineHowToReg, MdAdminPanelSettings, MdOutlineClass } from 'react-icons/md';
import { RiAiGenerate } from 'react-icons/ri';
import { BiLeaf } from 'react-icons/bi';
import { PiStudentBold, PiChalkboardTeacherBold } from 'react-icons/pi';
import { HiOutlineCollection, HiOutlineLightBulb } from 'react-icons/hi';
import { FaPencil } from 'react-icons/fa6';
import { IoTimer } from 'react-icons/io5';
import Header from '../components/common/Header';
import Footer from '../components/common/Footer';
import API_BASE_URL from '../config/api';
import { useUser } from '../contexts/UserContext';
import Toast from '../components/common/Toast';
import Modal from '../components/common/Modal';
import ConfirmDialog from '../components/common/ConfirmDialog';
import { formatDateTime } from '../utils/dateUtils';

interface PendingTeacher {
    user_id: number;
    email: string;
    full_name: string;
    institution: string;
    proof_document_url: string | null;
    created_at: string | null;
}

interface FeedbackItem {
    id: number;
    type: 'report' | 'material_rating' | 'teacher_rating' | 'reference';
    user_name: string;
    user_role: string;
    course_name?: string;
    course_id?: number;
    content_name?: string;
    content_id?: number;
    title: string;
    description: string;
    rating?: number;
    tags?: string[];
    status?: string;  // only for 'report': 'pending' | 'done'
    created_at: string;
}

// Custom floating dropdown used in Course Management filters
const AdminDropdown = ({
    value,
    onChange,
    options,
    placeholder,
}: {
    value: string;
    onChange: (val: string) => void;
    options: { value: string; label: string }[];
    placeholder: string;
}) => {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const selected = options.find(o => o.value === value)?.label || placeholder;
    const active = value && value !== 'all';

    return (
        <div className="relative shrink-0" ref={ref}>
            <button
                onClick={() => setOpen(v => !v)}
                className={`flex items-center gap-2 px-4 py-1.5 rounded-2xl text-sm font-bold transition-all outline-none border-2 ${open
                    ? 'bg-white border-blue-400 text-slate-700 shadow-sm'
                    : active
                        ? 'bg-blue-50 border-blue-200 text-blue-600'
                        : 'bg-slate-50 border-transparent text-slate-500 hover:border-slate-200'
                    }`}
            >
                <span className="whitespace-nowrap">{selected}</span>
                <svg className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            {open && (
                <div className="absolute top-full left-0 mt-2 min-w-[160px] bg-white border border-slate-200 rounded-2xl shadow-xl z-50 py-1.5 overflow-hidden">
                    <div
                        className={`px-4 py-2.5 text-sm cursor-pointer transition-colors ${!active ? 'bg-blue-50 text-blue-600 font-bold' : 'text-slate-500 hover:bg-slate-50'
                            }`}
                        onClick={() => { onChange('all'); setOpen(false); }}
                    >
                        {placeholder}
                    </div>
                    {options.map(opt => (
                        <div
                            key={opt.value}
                            className={`px-4 py-2.5 text-sm cursor-pointer transition-colors ${value === opt.value
                                ? 'bg-blue-50 text-blue-600 font-bold'
                                : 'text-slate-700 hover:bg-slate-50'
                                }`}
                            onClick={() => { onChange(opt.value); setOpen(false); }}
                        >
                            {opt.label}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default function AdminPage() {
    const { user } = useUser();
    const navigate = useNavigate();
    const [teachers, setTeachers] = useState<PendingTeacher[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [actionLoading, setActionLoading] = useState<number | null>(null);
    const [isScrolled, setIsScrolled] = useState(false);

    useEffect(() => {
        const handleScroll = () => {
            setIsScrolled(window.scrollY > 20);
        };
        window.addEventListener('scroll', handleScroll);
        return () => window.removeEventListener('scroll', handleScroll);
    }, []);
    const [rejectReason, setRejectReason] = useState<Record<number, string>>({});
    const [rejectingId, setRejectingId] = useState<number | null>(null);
    const [activeTab, setActiveTab] = useState<'courses' | 'review' | 'users' | 'feedback' | 'experiment'>('experiment');
    const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
    const [allCourses, setAllCourses] = useState<any[]>([]);
    const [feedbackItems, setFeedbackItems] = useState<FeedbackItem[]>([]);
    const [filterSemester, setFilterSemester] = useState('all');
    const [filterTeacher, setFilterTeacher] = useState('all');
    const [feedbackCat, setFeedbackCat] = useState('all');

    // User Management State
    const [searchKeyword, setSearchKeyword] = useState('');
    const [searchResults, setSearchResults] = useState<any[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [statsUser, setStatsUser] = useState<any | null>(null);
    const [userStats, setUserStats] = useState<any>(null);
    const [isDeleting, setIsDeleting] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState<{ show: boolean; userId: number | null; userName: string }>({ show: false, userId: null, userName: '' });
    const [systemStats, setSystemStats] = useState<{
        teachers: number;
        students: number;
        courses: number;
        ai_generations: number;
        course_views: number;
        pending_teachers: number;
    } | null>(null);
    const [experimentStats, setExperimentStats] = useState<{
        teacher_stats: any;
        student_stats: any;
        daily_stats: any[];
        edit_ratio_distribution: any[];
        reading_engagement: any[];
        feedback_stats: any;
        rq_metrics: any;
        summarized_metrics?: any;
        kp_source_types?: Record<string, string>;
    } | null>(null);
    const [selectedExpCourse, setSelectedExpCourse] = useState('all');
    const [selectedExpUnit, setSelectedExpUnit] = useState('all');
    const [expUnits, setExpUnits] = useState<any[]>([]);
    const [rq1PageIndex, setRq1PageIndex] = useState(0);
    const [showSavedOnly, setShowSavedOnly] = useState(false);
    const [filterShortEdits, setFilterShortEdits] = useState(true);
    const [selectedGeneration, setSelectedGeneration] = useState<any>(null);
    const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
    const [srlTooltip, setSrlTooltip] = useState<{ x: number; y: number; students: any[]; dim: any; isLocked?: boolean } | null>(null);
    const srlTooltipRef = useRef<HTMLDivElement>(null);
    const itemsPerPage = 7;
    const token = sessionStorage.getItem('access_token') || '';
    const authHeader = { Authorization: `Bearer ${token}` };

    // Security Check
    useEffect(() => {
        if (user && user.role !== 'admin') {
            navigate('/');
        }
    }, [user, navigate]);

    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (srlTooltip?.isLocked) {
                // If clicked inside the tooltip, don't dismiss
                if (srlTooltipRef.current && srlTooltipRef.current.contains(e.target as Node)) {
                    return;
                }
                setSrlTooltip(null);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [srlTooltip]);

    const fetchPending = useCallback(async () => {
        setIsLoading(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/admin/teachers/pending`, {
                headers: authHeader,
            });
            if (!res.ok) throw new Error('無法取得待審核清單');
            const data = await res.json();
            setTeachers(data.pending_teachers || []);
        } catch (err) {
            setToast({ message: err instanceof Error ? err.message : '載入失敗', type: 'error' });
        } finally {
            setIsLoading(false);
        }
    }, [token]);

    const fetchCourses = useCallback(async () => {
        setIsLoading(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/admin/courses`, {
                headers: authHeader,
            });
            if (!res.ok) throw new Error('無法取得課程列表');
            const data = await res.json();
            setAllCourses((data || []).filter((c: any) => c.id === 61 || c.id === 62 || c.id === 11));
        } catch (err) {
            setToast({ message: err instanceof Error ? err.message : '載入課程失敗', type: 'error' });
        } finally {
            setIsLoading(false);
        }
    }, [token]);

    const fetchSystemStats = useCallback(async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/admin/system/stats`, {
                headers: authHeader,
            });
            if (!res.ok) throw new Error('無法取得系統統計資料');
            const data = await res.json();
            setSystemStats(data);
        } catch (err) {
            console.error(err);
        }
    }, [token]);

    useEffect(() => {
        fetchSystemStats();
    }, [fetchSystemStats]);

    const fetchFeedback = useCallback(async () => {
        setIsLoading(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/admin/feedback/all`, {
                headers: authHeader,
            });
            if (!res.ok) throw new Error('無法取得回饋列表');
            const data = await res.json();
            setFeedbackItems(data || []);
        } catch (err) {
            setToast({ message: err instanceof Error ? err.message : '載入回饋失敗', type: 'error' });
        } finally {
            setIsLoading(false);
        }
    }, [token]);

    const fetchExperimentStats = useCallback(async (courseId?: string, unitId?: string) => {
        setIsLoading(true);
        try {
            let url = `${API_BASE_URL}/api/admin/experiment/stats?days=30`;
            if (courseId && courseId !== 'all') url += `&course_id=${courseId}`;
            if (unitId && unitId !== 'all') url += `&unit_id=${unitId}`;

            const res = await fetch(url, {
                headers: authHeader,
            });
            if (!res.ok) throw new Error('無法取得實驗統計');
            const data = await res.json();
            setExperimentStats(data);
        } catch (err) {
            setToast({ message: err instanceof Error ? err.message : '載入統計失敗', type: 'error' });
        } finally {
            setIsLoading(false);
        }
    }, [token]);

    const fetchUnitsForCourse = useCallback(async (courseId: string) => {
        if (!courseId || courseId === 'all') {
            setExpUnits([]);
            return;
        }
        try {
            const res = await fetch(`${API_BASE_URL}/api/courses/${courseId}/units`, {
                headers: authHeader,
            });
            if (res.ok) {
                const data = await res.json();
                setExpUnits(data || []);
            }
        } catch (err) {
            console.error('Failed to fetch units', err);
        }
    }, [token]);

    useEffect(() => {
        if (activeTab === 'review') {
            fetchPending();
        } else if (activeTab === 'courses') {
            fetchCourses();
        } else if (activeTab === 'feedback') {
            fetchFeedback();
        } else if (activeTab === 'experiment') {
            fetchExperimentStats(selectedExpCourse, selectedExpUnit);
            fetchCourses();
        }
    }, [fetchPending, fetchCourses, fetchFeedback, fetchExperimentStats, activeTab, selectedExpCourse, selectedExpUnit]);

    useEffect(() => {
        if (selectedExpCourse && selectedExpCourse !== 'all') {
            fetchUnitsForCourse(selectedExpCourse);
        } else {
            setExpUnits([]);
        }
    }, [selectedExpCourse, fetchUnitsForCourse]);

    const handleApprove = async (userId: number) => {
        setActionLoading(userId);
        try {
            const res = await fetch(`${API_BASE_URL}/api/admin/teachers/approve`, {
                method: 'POST',
                headers: { ...authHeader, 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '審核失敗');
            setToast({ message: data.message, type: 'success' });
            setTeachers(prev => prev.filter(t => t.user_id !== userId));
        } catch (err) {
            setToast({ message: err instanceof Error ? err.message : '操作失敗', type: 'error' });
        } finally {
            setActionLoading(null);
        }
    };

    const handleReject = async (userId: number) => {
        setActionLoading(userId);
        try {
            const res = await fetch(`${API_BASE_URL}/api/admin/teachers/reject`, {
                method: 'POST',
                headers: { ...authHeader, 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, reason: rejectReason[userId] || '' }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '拒絕失敗');
            setToast({ message: data.message, type: 'success' });
            setTeachers(prev => prev.filter(t => t.user_id !== userId));
            setRejectingId(null);
        } catch (err) {
            setToast({ message: err instanceof Error ? err.message : '操作失敗', type: 'error' });
        } finally {
            setActionLoading(null);
        }
    };

    const handleSearchUsers = async () => {
        if (!searchKeyword.trim()) return;
        setIsSearching(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/admin/users/search?keyword=${encodeURIComponent(searchKeyword)}`, {
                headers: authHeader
            });
            if (!res.ok) throw new Error('搜尋失敗');
            const data = await res.json();
            setSearchResults(data);
        } catch (err) {
            setToast({ message: '搜尋使用者失敗', type: 'error' });
        } finally {
            setIsSearching(false);
        }
    };

    const fetchUserStats = async (u: any) => {
        setStatsUser(u);
        setUserStats(null);
        try {
            const res = await fetch(`${API_BASE_URL}/api/admin/users/${u.id}/stats`, {
                headers: authHeader
            });
            if (!res.ok) throw new Error('無法取得統計資料');
            const data = await res.json();
            setUserStats(data);
        } catch (err) {
            setToast({ message: '載入統計失敗', type: 'error' });
        }
    };

    const handleDeleteUser = async (userId: number) => {
        setIsDeleting(true);
        try {
            const res = await fetch(`${API_BASE_URL}/api/admin/users/${userId}`, {
                method: 'DELETE',
                headers: authHeader
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '刪除失敗');
            setToast({ message: '使用者已成功刪除', type: 'success' });
            setConfirmDelete({ show: false, userId: null, userName: '' });
            setSearchResults(prev => prev.filter(u => u.id !== userId));
            setStatsUser(null);
        } catch (err) {
            setToast({ message: err instanceof Error ? err.message : '刪除失敗', type: 'error' });
        } finally {
            setIsDeleting(false);
        }
    };

    const handleSaveSeed = async (jobId: number) => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/admin/experiment/seeds`, {
                method: 'POST',
                headers: { ...authHeader, 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: jobId }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '儲存失敗');
            setToast({ message: `成功存為實驗種子 (Seed ID: ${data.data.seed_id})`, type: 'success' });
        } catch (err) {
             setToast({ message: err instanceof Error ? err.message : '儲存失敗', type: 'error' });
        }
    };

    const formatDate = (iso: string | null) => {
        return formatDateTime(iso);
    };

    return (
        <div className="min-h-screen bg-slate-50 flex flex-col relative">
            {/* Background Decoration Wrapper to prevent horizontal overflow while keeping sticky functional */}
            <div className="absolute top-0 left-0 w-full h-[500px] overflow-hidden pointer-events-none z-0">
                <div className="w-full h-full bg-[linear-gradient(to_right,#DBEAFE,#eff6ff,#DBEAFE)] [mask-image:linear-gradient(to_bottom,white,transparent)] rounded-b-[30%] scale-x-125 opacity-60" />
            </div>

            <div className={`sticky top-0 z-50 transition-all duration-300 ${isScrolled ? 'bg-[#f0f7ff]' : 'bg-transparent'}`}>
                <Header paths={[
                    { name: "管理中心", path: "/admin" }
                ]} />
            </div>

            <main className="flex-1 px-8 py-8 relative z-10 w-full">
                {/* Dashboard Top Section - Title & Stats */}
                <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6 mb-4">
                    <div className="flex items-center gap-4">
                        <div className="w-14 h-14 rounded-2xl bg-white shadow-xl shadow-blue-100 flex items-center justify-center text-blue-600 border border-blue-50 transition-transform hover:scale-110">
                            <MdAdminPanelSettings size={32} />
                        </div>
                        <div>
                            <h1 className="text-3xl font-extrabold text-slate-800 tracking-tight">管理中心</h1>
                        </div>
                    </div>

                    {/* Stats Cards Grid - Optimized width and spacing */}
                    <div className="flex flex-wrap lg:flex-nowrap gap-3">
                        {[
                            { label: '授課教師', value: systemStats?.teachers ?? '—', icon: PiChalkboardTeacherBold, color: 'orange' },
                            { label: '註冊學生', value: systemStats?.students ?? '—', icon: PiStudentBold, color: 'green' },
                            { label: '系統課程', value: systemStats?.courses ?? '—', icon: FaBook, color: 'blue' },
                            { label: 'AI內容生成', value: systemStats?.ai_generations ?? '—', icon: FiZap, color: 'yellow' },
                            { label: '教材閱讀次數', value: systemStats?.course_views ?? '—', icon: FiEye, color: 'purple' },
                        ].map((stat, idx) => (
                            <div key={idx} className="bg-white/60 backdrop-blur-sm px-4 py-2.5 rounded-2xl border border-white shadow-sm flex items-center gap-3 group hover:bg-white hover:shadow-md transition-all min-w-[140px]">
                                <div className={`w-9 h-9 rounded-xl flex items-center justify-center bg-${stat.color}-50 text-${stat.color}-500 group-hover:bg-${stat.color}-500 group-hover:text-white transition-all shrink-0`}>
                                    <stat.icon size={18} />
                                </div>
                                <div className="text-left min-w-0">
                                    <div className="text-xl font-black text-slate-800 leading-none mb-0.5 truncate">{stat.value}</div>
                                    <div className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider truncate">{stat.label}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                <div className={`sticky top-[56px] z-40 flex flex-wrap items-center justify-between py-3 mb-6 shrink-0 gap-6 -mx-8 px-8 transition-all duration-300 ${isScrolled ? 'bg-[#f0f7ff] shadow-lg border-b border-slate-200' : ''}`}>
                    <div className="bg-slate-200/40 p-1 rounded-xl inline-flex gap-1 backdrop-blur-sm border border-slate-200/60 shadow-inner">
                        {[
                            { id: 'courses', label: '課程管理', icon: MdOutlineClass },
                            { id: 'review', label: '教師審核', icon: MdOutlineHowToReg, count: teachers.length },
                            { id: 'users', label: '使用者管理', icon: FiUsers },
                            { id: 'feedback', label: '使用者回饋', icon: FiMessageSquare, count: feedbackItems.filter(f => f.type === 'report').length },
                            { id: 'experiment', label: '教師實驗監測', icon: AiTwotoneExperiment },
                        ].map((tab) => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id as any)}
                                className={`
                                    relative py-2.5 px-5 rounded-xl text-sm font-bold transition-all duration-300 flex items-center justify-center gap-2 whitespace-nowrap
                                    ${activeTab === tab.id
                                        ? 'bg-white text-blue-600 shadow-md transform scale-[1.02]'
                                        : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50/50'
                                    }
                                `}
                            >
                                <tab.icon size={18} />
                                {tab.label}
                                {'count' in tab && (
                                    <span className={`absolute -top-1 -right-1 inline-flex items-center justify-center w-4 h-4 rounded-full text-[9px] font-black transition-all ${(tab.count ?? 0) > 0
                                        ? activeTab === tab.id
                                            ? 'bg-blue-600 text-white shadow-sm'
                                            : 'bg-red-500 text-white'
                                        : 'opacity-0 pointer-events-none'
                                        }`}>
                                        {tab.count ?? 0}
                                    </span>
                                )}
                            </button>
                        ))}
                    </div>

                    {activeTab === 'experiment' && (
                        <div className="flex items-center gap-3 animate-in fade-in slide-in-from-right-4 duration-500">
                            <div className="flex items-center gap-2 bg-white p-1 rounded-xl border border-slate-200 shadow-sm">
                                <BsClipboardDataFill className="text-indigo-400 ml-2" size={14} />
                                <AdminDropdown
                                    value={selectedExpCourse}
                                    onChange={(val) => {
                                        setSelectedExpCourse(val);
                                        setSelectedExpUnit('all');
                                    }}
                                    placeholder="全部課程"
                                    options={[
                                        { value: 'all', label: '全部實驗課程' },
                                        ...allCourses
                                            .filter((c: any) => [11, 61, 62].includes(Number(c.id)))
                                            .map((c: any) => ({ value: c.id.toString(), label: c.name }))
                                    ]}
                                />
                            </div>
                            <div className="flex items-center gap-2 bg-white p-1 rounded-xl border border-slate-200 shadow-sm">
                                <HiOutlineCollection className="text-blue-400 ml-2" size={14} />
                                <AdminDropdown
                                    value={selectedExpUnit}
                                    onChange={setSelectedExpUnit}
                                    placeholder="全部單元"
                                    options={[
                                        { value: 'all', label: '全部單元數據' },
                                        ...expUnits.map((u: any) => ({ value: u.id.toString(), label: u.name }))
                                    ]}
                                />
                            </div>
                            <button
                                onClick={() => fetchExperimentStats(selectedExpCourse, selectedExpUnit)}
                                className="px-3 py-2.5 bg-blue-600 text-white text-xs font-bold rounded-lg hover:bg-blue-700 transition-all shadow-md shadow-blue-100 flex items-center gap-2 group"
                            >
                                <FiRefreshCw className="group-hover:rotate-180 transition-all duration-500" size={14} />
                                刷新數據
                            </button>
                        </div>
                    )}
                </div>

                {/* Content Area */}
                <div className="space-y-6">
                    {activeTab === 'review' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                            <div className="flex items-center justify-between mb-6 px-2">
                                <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                                    待審核申請
                                    <span className="text-sm font-medium text-slate-400">({teachers.length})</span>
                                </h3>
                                <button
                                    onClick={fetchPending}
                                    disabled={isLoading}
                                    className="p-2 text-blue-600 hover:bg-blue-50 rounded-xl transition-all disabled:opacity-50 group"
                                    title="重新整理"
                                >
                                    <FiRefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : 'group-hover:rotate-180 transition-transform duration-500'}`} />
                                </button>
                            </div>

                            {isLoading ? (
                                <div className="flex flex-col items-center justify-center py-32 text-slate-400 gap-4">
                                    <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin shadow-lg" />
                                    <p className="font-medium">載入中...</p>
                                </div>
                            ) : teachers.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-24 text-slate-400 gap-3">
                                    <MdOutlineHowToReg size={40} className="text-slate-200" />
                                    <p className="font-bold text-slate-400">目前沒有待處理的申請</p>
                                </div>
                            ) : (
                                <div className="grid gap-6">
                                    {teachers.map(teacher => (
                                        <div
                                            key={teacher.user_id}
                                            className="bg-white rounded-[32px] p-8 border border-white shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-[0_20px_40px_rgba(0,0,0,0.08)] transition-all duration-300 group"
                                        >
                                            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-8">
                                                <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-6">
                                                    <div className="space-y-6">
                                                        <div className="flex items-center gap-4">
                                                            <div className="w-12 h-12 rounded-2xl bg-blue-50 text-blue-500 flex items-center justify-center transition-colors group-hover:bg-blue-600 group-hover:text-white">
                                                                <FiUser size={20} />
                                                            </div>
                                                            <div>
                                                                <p className="text-xs text-slate-400 font-bold uppercase tracking-wider mb-0.5">申請姓名</p>
                                                                <p className="text-lg font-bold text-slate-800">{teacher.full_name}</p>
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-4">
                                                            <div className="w-12 h-12 rounded-2xl bg-slate-50 text-slate-400 flex items-center justify-center">
                                                                <FiMail size={20} />
                                                            </div>
                                                            <div className="min-w-0">
                                                                <p className="text-xs text-slate-400 font-bold uppercase tracking-wider mb-0.5">電子郵件</p>
                                                                <p className="text-slate-600 font-medium truncate">{teacher.email}</p>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    <div className="space-y-6">
                                                        <div className="flex items-center gap-4">
                                                            <div className="w-12 h-12 rounded-2xl bg-slate-50 text-slate-400 flex items-center justify-center">
                                                                <FiFileText size={20} />
                                                            </div>
                                                            <div>
                                                                <p className="text-xs text-slate-400 font-bold uppercase tracking-wider mb-0.5">學校機構</p>
                                                                <p className="text-slate-700 font-bold">{teacher.institution}</p>
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-4">
                                                            <div className="w-12 h-12 rounded-2xl bg-slate-50 text-slate-400 flex items-center justify-center">
                                                                <FiCalendar size={20} />
                                                            </div>
                                                            <div>
                                                                <p className="text-xs text-slate-400 font-bold uppercase tracking-wider mb-0.5">申請日期</p>
                                                                <p className="text-slate-600 font-medium">{formatDate(teacher.created_at)}</p>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>

                                                <div className="flex flex-col gap-3 min-w-[180px]">
                                                    {teacher.proof_document_url && (
                                                        <a
                                                            href={`${API_BASE_URL}/${teacher.proof_document_url}`}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="flex items-center justify-center gap-2 px-6 py-3 bg-slate-100 text-slate-600 rounded-2xl text-sm font-bold hover:bg-slate-200 transition-colors"
                                                        >
                                                            <FiFileText />
                                                            檢視證明文件
                                                        </a>
                                                    )}

                                                    {rejectingId !== teacher.user_id ? (
                                                        <div className="flex flex-col gap-3">
                                                            <button
                                                                onClick={() => handleApprove(teacher.user_id)}
                                                                disabled={actionLoading === teacher.user_id}
                                                                className="flex items-center justify-center gap-2 px-6 py-3.5 bg-blue-600 text-white rounded-2xl font-bold hover:bg-blue-700 hover:-translate-y-0.5 transition-all shadow-lg shadow-blue-200 disabled:opacity-50"
                                                            >
                                                                <FiCheck />
                                                                確認通過
                                                            </button>
                                                            <button
                                                                onClick={() => setRejectingId(teacher.user_id)}
                                                                disabled={actionLoading === teacher.user_id}
                                                                className="flex items-center justify-center gap-2 px-6 py-3 text-slate-400 bg-white border border-slate-200 rounded-2xl font-bold hover:text-red-600 hover:border-red-200 hover:bg-red-50 transition-all disabled:opacity-50"
                                                            >
                                                                <FiX />
                                                                拒絕申請
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <div className="w-full lg:w-72 animate-in fade-in zoom-in-95 duration-200">
                                                            <textarea
                                                                value={rejectReason[teacher.user_id] || ''}
                                                                onChange={(e) => setRejectReason(prev => ({ ...prev, [teacher.user_id]: e.target.value }))}
                                                                placeholder="請輸入拒絕原因 (選填)"
                                                                rows={3}
                                                                className="w-full p-4 text-sm border-2 border-slate-100 rounded-2xl focus:border-red-400 focus:ring-4 focus:ring-red-50 outline-none mb-3 transition-all"
                                                            />
                                                            <div className="grid grid-cols-2 gap-3">
                                                                <button
                                                                    onClick={() => setRejectingId(null)}
                                                                    className="py-2.5 text-slate-500 font-bold hover:bg-slate-50 rounded-xl transition-colors"
                                                                >
                                                                    取消
                                                                </button>
                                                                <button
                                                                    onClick={() => handleReject(teacher.user_id)}
                                                                    className="py-2.5 bg-red-500 text-white font-bold rounded-xl hover:bg-red-600 shadow-lg shadow-red-100 transition-all"
                                                                >
                                                                    確認拒絕
                                                                </button>
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === 'courses' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                            {/* Course Search & Filter Section */}
                            <div className="bg-white/60 backdrop-blur-md p-6 rounded-[32px] shadow-sm border border-white mb-8">
                                <div className="flex flex-col md:flex-row gap-4">
                                    <div className="relative flex-1">
                                        <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-slate-400">
                                            <FiSearch />
                                        </div>
                                        <input
                                            type="text"
                                            value={searchKeyword}
                                            onChange={(e) => setSearchKeyword(e.target.value)}
                                            placeholder="搜尋課程名稱、學期或教師..."
                                            className="w-full pl-11 pr-4 py-3.5 bg-slate-50 border-2 border-transparent focus:border-blue-400 focus:bg-white rounded-2xl outline-none transition-all font-medium"
                                        />
                                    </div>
                                    <div className="flex gap-2">
                                        <AdminDropdown
                                            value={filterSemester}
                                            onChange={setFilterSemester}
                                            placeholder="所有學期"
                                            options={[...new Set(allCourses.map(c => c.semester).filter(Boolean))].sort().reverse().map(s => ({ value: s, label: s }))}
                                        />
                                        <AdminDropdown
                                            value={filterTeacher}
                                            onChange={setFilterTeacher}
                                            placeholder="授課教師"
                                            options={[...new Set(allCourses.map(c => c.teacher_name).filter(Boolean))].sort().map(t => ({ value: t, label: t }))}
                                        />
                                    </div>
                                </div>
                            </div>

                            {isLoading ? (
                                <div className="flex flex-col items-center justify-center py-32 text-slate-400 gap-4">
                                    <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin shadow-lg" />
                                    <p className="font-medium">載入中...</p>
                                </div>
                            ) : allCourses.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-32 bg-white/40 backdrop-blur-sm rounded-[40px] border border-slate-200 border-dashed text-slate-400 gap-4">
                                    <div className="w-20 h-20 rounded-full bg-slate-50 flex items-center justify-center text-slate-200">
                                        <HiOutlineCollection size={48} />
                                    </div>
                                    <p className="text-xl font-bold text-slate-400">目前系統中沒有課程</p>
                                </div>
                            ) : (
                                <div className="grid gap-4">
                                    {allCourses
                                        .filter(c =>
                                            (!searchKeyword ||
                                                c.name?.toLowerCase().includes(searchKeyword.toLowerCase()) ||
                                                c.teacher_name?.toLowerCase().includes(searchKeyword.toLowerCase()) ||
                                                c.semester?.toLowerCase().includes(searchKeyword.toLowerCase())) &&
                                            (filterSemester === 'all' || c.semester === filterSemester) &&
                                            (filterTeacher === 'all' || c.teacher_name === filterTeacher)
                                        )
                                        .map(course => (
                                            <div key={course.id} className="bg-white p-6 rounded-3xl border border-white shadow-[0_4px_20px_rgba(0,0,0,0.03)] flex items-center justify-between group hover:shadow-xl hover:shadow-blue-900/5 transition-all duration-300">
                                                <div className="flex items-center gap-5">
                                                    <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center text-blue-500 font-bold group-hover:bg-blue-600 group-hover:text-white transition-all">
                                                        <MdOutlineClass size={24} />
                                                    </div>
                                                    <div>
                                                        <h4 className="text-lg font-bold text-slate-800 mb-0.5">{course.name}</h4>
                                                        <p className="text-sm text-slate-400 font-bold uppercase tracking-wider">{course.semester} <span className="mx-2 opacity-30">|</span> 授課老師：{course.teacher_name}</p>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-3">
                                                    <button
                                                        onClick={() => navigate(`/teacher/courses/${course.id}`)}
                                                        className="px-6 py-3 bg-slate-50 text-slate-600 font-bold rounded-xl hover:bg-blue-600 hover:text-white transition-all flex items-center gap-2 group/btn"
                                                    >
                                                        進入課程
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === 'feedback' && (() => {
                        const feedbackCategories = [
                            { id: 'all', label: '全部' },
                            { id: 'report', label: '問題回報' },
                            { id: 'material_rating', label: '學生評教材' },
                            { id: 'teacher_rating', label: '生成品質' },
                            { id: 'reference', label: '引用來源' },
                        ];
                        const visibleFeedback = feedbackCat === 'all'
                            ? feedbackItems
                            : feedbackItems.filter(f => f.type === feedbackCat);

                        const typeLabel: Record<string, string> = {
                            report: '問題回報',
                            material_rating: '學生評教材',
                            teacher_rating: '生成品質',
                            reference: '引用來源',
                        };
                        const typeCls: Record<string, string> = {
                            report: 'bg-red-100 text-red-600',
                            material_rating: 'bg-amber-100 text-amber-600',
                            teacher_rating: 'bg-blue-100 text-blue-600',
                            reference: 'bg-purple-100 text-purple-600',
                        };

                        const handleMarkDone = async (reportId: number, currentStatus: string) => {
                            const newStatus = currentStatus === 'done' ? 'pending' : 'done';
                            try {
                                const res = await fetch(`${API_BASE_URL}/api/admin/feedback/reports/${reportId}/status?status=${newStatus}`, {
                                    method: 'PATCH',
                                    headers: authHeader,
                                });
                                if (res.ok) {
                                    setFeedbackItems(prev => prev.map(item =>
                                        item.id === reportId && item.type === 'report'
                                            ? { ...item, status: newStatus }
                                            : item
                                    ));
                                }
                            } catch (err) {
                                console.error('Failed to update report status', err);
                            }
                        };

                        return (
                            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                                {/* Header row: title + category tabs + refresh */}
                                <div className="flex items-center gap-3 mb-6 px-2 flex-wrap">
                                    <h3 className="text-xl font-bold text-slate-800 whitespace-nowrap">
                                        使用者回饋
                                    </h3>

                                    {/* Category sub-tabs inline */}
                                    <div className="flex gap-1.5 flex-wrap flex-1">
                                        {feedbackCategories.map(cat => (
                                            <button
                                                key={cat.id}
                                                onClick={() => setFeedbackCat(cat.id)}
                                                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${feedbackCat === cat.id
                                                    ? 'bg-blue-600 text-white shadow-md'
                                                    : 'bg-white text-slate-500 border border-slate-200 hover:border-blue-200 hover:text-blue-500'
                                                    }`}
                                            >
                                                {cat.label}
                                            </button>
                                        ))}
                                    </div>

                                    <button
                                        onClick={fetchFeedback}
                                        disabled={isLoading}
                                        className="p-2 text-blue-600 hover:bg-blue-50 rounded-xl transition-all disabled:opacity-50 group"
                                        title="重新整理"
                                    >
                                        <FiRefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : 'group-hover:rotate-180 transition-transform duration-500'}`} />
                                    </button>
                                </div>

                                {isLoading ? (
                                    <div className="flex flex-col items-center justify-center py-32 text-slate-400 gap-4">
                                        <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin shadow-lg" />
                                        <p className="font-medium">載入中...</p>
                                    </div>
                                ) : visibleFeedback.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center py-24 text-slate-400 gap-3">
                                        <FiMessageSquare size={40} className="text-slate-200" />
                                        <p className="font-bold text-slate-400">目前沒有任何回饋</p>
                                    </div>
                                ) : (
                                    <div className="grid gap-4">
                                        {visibleFeedback.map(item => (
                                            <div key={`${item.type}-${item.id}`} className="bg-white rounded-2xl p-6 border border-slate-100 shadow-sm hover:shadow-md transition-all duration-200">
                                                <div className="flex items-start gap-4">
                                                    <div className="flex-1 min-w-0 space-y-3">
                                                        {/* Top row: type badge + date + user + course meta */}
                                                        <div className="flex items-center gap-2 flex-wrap">
                                                            <span className={`px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-wider ${typeCls[item.type] ?? 'bg-slate-100 text-slate-500'}`}>
                                                                {typeLabel[item.type] ?? item.type}
                                                            </span>
                                                            <span className="text-xs text-slate-400 font-medium">{formatDate(item.created_at)}</span>

                                                            {/* User chip */}
                                                            <div className="flex items-center gap-1 text-xs text-slate-500 bg-slate-50 px-2 py-1 rounded-lg border border-slate-100">
                                                                <FiUser size={10} />
                                                                <span className="font-bold">{item.user_name}</span>
                                                                <span className="text-[10px] text-slate-400 uppercase">{item.user_role}</span>
                                                            </div>

                                                            {item.course_name && (
                                                                <div className="flex items-center gap-1 text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded-lg border border-blue-100">
                                                                    <FaBook size={10} />
                                                                    <span className="font-bold">{item.course_name}</span>
                                                                </div>
                                                            )}
                                                        </div>

                                                        {/* Title */}
                                                        <h4 className="font-bold text-slate-800 truncate">{item.title}</h4>

                                                        {/* Description */}
                                                        {item.description && item.description !== '無文字回饋' && (
                                                            <p className="text-sm text-slate-600 leading-relaxed bg-slate-50 px-3 py-2 rounded-xl border border-slate-100">
                                                                {item.description}
                                                            </p>
                                                        )}

                                                        {/* Star rating */}
                                                        {item.rating != null && (
                                                            <div className="flex items-center gap-1">
                                                                {[1, 2, 3, 4, 5].map(s => (
                                                                    <span key={s} className={`text-base ${s <= item.rating! ? 'text-amber-600' : 'text-slate-200'}`}>★</span>
                                                                ))}
                                                                <span className="text-xs text-slate-400 ml-1">{item.rating}/5</span>
                                                            </div>
                                                        )}

                                                        {/* Tags */}
                                                        {item.tags && item.tags.length > 0 && (
                                                            <div className="flex flex-wrap gap-1.5">
                                                                {item.tags.map(tag => (
                                                                    <span key={tag} className="px-2 py-1 bg-slate-100 text-slate-500 rounded-lg text-[10px] font-bold">#{tag}</span>
                                                                ))}
                                                            </div>
                                                        )}

                                                    </div>

                                                    {/* Action column */}
                                                    <div className="flex flex-col gap-2 shrink-0">
                                                        {item.type === 'report' && (
                                                            <button
                                                                onClick={() => handleMarkDone(item.id, item.status ?? 'pending')}
                                                                className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-bold transition-all ${item.status === 'done'
                                                                    ? 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100 border border-emerald-200'
                                                                    : 'bg-slate-100 text-slate-500 hover:bg-slate-200 border border-slate-200'
                                                                    }`}
                                                                title={item.status === 'done' ? '點擊撤銷已處理' : '標記為已處理'}
                                                            >
                                                                <FiCheck size={13} />
                                                                {item.status === 'done' ? '已處理' : '標記處理'}
                                                            </button>
                                                        )}
                                                        {item.course_id && (
                                                            <button
                                                                onClick={() => navigate(`/teacher/courses/${item.course_id}`)}
                                                                className="flex items-center gap-1.5 px-4 py-2 bg-blue-50 text-blue-600 rounded-xl text-sm font-bold hover:bg-blue-600 hover:text-white transition-all"
                                                            >
                                                                <FiEye size={14} />
                                                                查看
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })()}

                    {activeTab === 'experiment' && experimentStats && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-6 pb-12">


                            {/* 3. Teacher Behavior Analysis Section */}
                            <div className="space-y-6">
                                <h4 className="flex items-center gap-3 text-2xl font-black text-slate-800">
                                    <span className="w-2 h-8 bg-blue-600 rounded-full shadow-lg shadow-blue-100" />
                                    教師行為分析 (Teacher Behavior Analysis)
                                </h4>

                                <div className="bg-slate-50/50 p-6 rounded-[40px] border border-slate-100 space-y-6">
                                    <div className="grid grid-cols-1 gap-6">

                                        {/* Teacher Insight Banner (New) */}
                                        <div className="bg-white border border-slate-100 p-8 rounded-[40px] shadow-sm overflow-hidden relative group/banner">
                                            <div className="absolute top-0 right-0 -mr-20 -mt-20 w-80 h-80 bg-indigo-500/5 blur-[100px] rounded-full group-hover/banner:scale-110 transition-transform duration-1000" />
                                            <div className="absolute bottom-0 left-0 -ml-20 -mb-20 w-80 h-80 bg-blue-500/5 blur-[100px] rounded-full group-hover/banner:scale-110 transition-transform duration-1000" />

                                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-x-0 relative z-10 p-2">
                                                {/* SECTION 1: RETRIEVAL QUALITY */}
                                                <div className="space-y-6 px-8">
                                                    <div className="border-b border-slate-100 pb-3">
                                                        <h6 className="text-lg font-black text-slate-800 flex items-center gap-2">
                                                            檢索品質 (TOP_K=10)
                                                        </h6>
                                                    </div>
                                                    <div className="space-y-4 px-1">
                                                        {[
                                                            { label: '關鍵字覆蓋率', key: 'keyword_coverage', value: `${((experimentStats.summarized_metrics?.rag_averages?.keyword_coverage || 0) * 100).toFixed(0)}%`, eng: 'keyword_coverage' },
                                                            { label: 'Top-1 相似度', key: 'top1_vector_score', value: (experimentStats.summarized_metrics?.rag_averages?.top1_vector_score || 0).toFixed(2), eng: 'top_vector' },
                                                            { label: '平均相似度', key: 'avg_vector_score', value: (experimentStats.summarized_metrics?.rag_averages?.avg_vector_score || 0).toFixed(2), eng: 'avg_vector' },
                                                            { label: 'BM25 命中數', key: 'bm25_hit_count', value: (experimentStats.summarized_metrics?.rag_averages?.bm25_hit_count || 0).toFixed(1), eng: 'bm25_hits' },
                                                            { label: '內容多樣性', key: 'diversity', value: `${experimentStats.summarized_metrics?.rag_averages?.diversity_chunks?.toFixed(0) || 0}/${experimentStats.summarized_metrics?.rag_averages?.diversity_pages?.toFixed(0) || 0}`, eng: 'chunks/pages' },
                                                            { label: '事實正確性', key: 'faithfulness', value: (experimentStats.summarized_metrics?.rag_averages?.faithfulness || 0).toFixed(2), eng: 'faithfulness' }
                                                        ].map(item => (
                                                            <div key={item.key} className="flex justify-between items-center group/metric">
                                                                <div className="flex items-center gap-3">
                                                                    <div className="w-2 h-2 rounded-full bg-blue-500/30 group-hover/metric:bg-blue-500 transition-colors" />
                                                                    <div className="flex flex-col">
                                                                        <span className="text-[13px] font-black text-slate-800 uppercase">{item.label}</span>
                                                                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">{item.eng}</span>
                                                                    </div>
                                                                </div>
                                                                <span className="text-xl font-black text-blue-500">{item.value}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>

                                                {/* SECTION 2: AI QUALITY ASSESSMENT */}
                                                <div className="space-y-6 border-l border-slate-100 px-8">
                                                    <div className="border-b border-slate-100 pb-3">
                                                        <h6 className="text-lg font-black text-slate-800 flex items-center gap-2">
                                                            AI 品質評估
                                                        </h6>
                                                    </div>
                                                    <div className="space-y-4 px-1">
                                                        {Object.entries(experimentStats.summarized_metrics?.ai_averages || {}).map(([key, val]: [string, any]) => (
                                                            <div key={key} className="flex justify-between items-center group/metric">
                                                                <div className="flex items-center gap-3">
                                                                    <div className="w-2 h-2 rounded-full bg-blue-500/30 group-hover/metric:bg-blue-500 transition-colors" />
                                                                    <div className="flex flex-col">
                                                                        <span className="text-[13px] font-black text-slate-800 uppercase">{key.split('(')[0].trim()}</span>
                                                                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter" title={key}>{key.includes('(') ? key.split('(')[1].replace(')', '') : key}</span>
                                                                    </div>
                                                                </div>
                                                                <span className={`text-xl font-black ${val >= 4 ? 'text-emerald-500' : val >= 3 ? 'text-blue-500' : 'text-amber-500'}`}>{val.toFixed(1)}</span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>

                                                {/* SECTION 3: TEACHER BEHAVIOR & ACTIONS */}
                                                <div className="space-y-6 border-l border-slate-100 px-8">
                                                    <div className="border-b border-slate-100 pb-3">
                                                        <h6 className="text-lg font-black text-slate-800 flex items-center gap-2">
                                                            教師行為分析
                                                        </h6>
                                                    </div>
                                                    <div className="space-y-5">
                                                        <div className="flex items-center justify-between">
                                                            <div className="flex items-center gap-2.5">
                                                                <FaPencil size={16} className="text-amber-500" />
                                                                <span className="text-[13px] font-black text-slate-800 uppercase tracking-widest">平均編修幅度</span>
                                                            </div>
                                                            <h4 className="text-2xl font-black text-amber-500 tracking-tighter">
                                                                {(experimentStats.summarized_metrics?.avg_edit_ratio * 100).toFixed(1)}%
                                                            </h4>
                                                        </div>
                                                        <div className="flex items-center justify-between">
                                                            <div className="flex items-center gap-2.5">
                                                                <IoTimer size={18} className="text-slate-400" />
                                                                <span className="text-[13px] font-black text-slate-800 uppercase tracking-widest">平均編修時間</span>
                                                            </div>
                                                            <div className="flex items-baseline gap-1">
                                                                <h4 className="text-2xl font-black text-slate-800 tracking-tighter">
                                                                    {(experimentStats.summarized_metrics?.avg_edit_time || 0) >= 60
                                                                        ? Math.floor(experimentStats.summarized_metrics.avg_edit_time / 60)
                                                                        : experimentStats.summarized_metrics?.avg_edit_time?.toFixed(0)}
                                                                </h4>
                                                                <span className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">{(experimentStats.summarized_metrics?.avg_edit_time || 0) >= 60 ? 'min' : 's'}</span>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    <div className="space-y-4 pt-4 border-t border-slate-50">
                                                        <div className="flex items-baseline gap-2 px-1">
                                                            <p className="text-[13px] font-black text-slate-800 uppercase tracking-widest">生成結果處置</p>
                                                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">Next Action Summary</p>
                                                        </div>
                                                        <div className="space-y-4 px-1">
                                                            {(() => {
                                                                const actionTotal = (experimentStats.summarized_metrics?.action_summary?.save || 0) +
                                                                    (experimentStats.summarized_metrics?.action_summary?.regenerate || 0) +
                                                                    (experimentStats.summarized_metrics?.action_summary?.discard || 0);
                                                                return [
                                                                    { label: '儲存', key: 'save', color: 'bg-emerald-500', count: experimentStats.summarized_metrics?.action_summary?.save || 0 },
                                                                    { label: '重新生成', key: 'regenerate', color: 'bg-amber-500', count: experimentStats.summarized_metrics?.action_summary?.regenerate || 0 },
                                                                    { label: '捨棄', key: 'discard', color: 'bg-rose-500', count: experimentStats.summarized_metrics?.action_summary?.discard || 0 }
                                                                ].map(act => {
                                                                    const pct = actionTotal > 0 ? (act.count / actionTotal) * 100 : 0;
                                                                    return (
                                                                        <div key={act.key} className="space-y-1.5 group/act">
                                                                            <div className="flex items-center justify-between">
                                                                                <div className="flex items-center gap-2">
                                                                                    <div className={`w-2 h-2 rounded-full ${act.color}`} />
                                                                                    <span className="text-sm font-bold text-slate-800">{act.label}</span>
                                                                                </div>
                                                                                <div className="flex items-baseline gap-1.5">
                                                                                    <span className="text-sm font-black text-slate-800">{pct.toFixed(0)}%</span>
                                                                                    <span className="text-[10px] font-bold text-slate-400">({act.count}次)</span>
                                                                                </div>
                                                                            </div>
                                                                            <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                                                                                <div
                                                                                    className={`h-full ${act.color} rounded-full transition-all duration-1000 ease-out`}
                                                                                    style={{ width: `${pct}%` }}
                                                                                />
                                                                            </div>
                                                                        </div>
                                                                    );
                                                                });
                                                            })()}
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* SECTION 4: OVERALL SCORES & COST */}
                                                <div className="space-y-6 border-l border-slate-100 px-8">
                                                    <div className="border-b border-slate-100 pb-3">
                                                        <h6 className="text-lg font-black text-slate-800 flex items-center gap-2">
                                                            綜合效能評估
                                                        </h6>
                                                    </div>
                                                    <div className="space-y-6">
                                                        {(() => {
                                                            const aiScores = Object.values(experimentStats?.summarized_metrics?.ai_averages || {});
                                                            const aiAvg = aiScores.length > 0 ? (aiScores.reduce((a: any, b: any) => a + b, 0) / aiScores.length) : 0;
                                                            const teacherAvg = experimentStats?.feedback_stats?.avg_rating || 0;

                                                            const getScoreColor = (score: number) => score >= 3.5 ? 'text-amber-500' : 'text-rose-500';

                                                            return (
                                                                <>
                                                                    <div className="flex justify-between items-center group/score">
                                                                        <div className="flex flex-col">
                                                                            <span className="text-[13px] font-black text-slate-800 uppercase tracking-widest">AI 品質平均分數</span>
                                                                            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">AI Evaluation Avg</span>
                                                                        </div>
                                                                        <div className="flex items-center gap-2">
                                                                            <FaStar className={getScoreColor(aiAvg)} size={16} />
                                                                            <div className="flex items-baseline gap-0.5">
                                                                                <h4 className={`text-2xl font-black ${getScoreColor(aiAvg)} tracking-tighter`}>
                                                                                    {aiAvg.toFixed(1)}
                                                                                </h4>
                                                                                <span className="text-[10px] text-slate-300 font-bold">/5</span>
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                    <div className="flex justify-between items-center group/score">
                                                                        <div className="flex flex-col">
                                                                            <span className="text-[13px] font-black text-slate-800 uppercase tracking-widest">教師平均滿意度</span>
                                                                            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">Teacher Rating Avg</span>
                                                                        </div>
                                                                        <div className="flex items-center gap-2">
                                                                            <FaStar className={getScoreColor(teacherAvg)} size={16} />
                                                                            <div className="flex items-baseline gap-0.5">
                                                                                <h4 className={`text-2xl font-black ${getScoreColor(teacherAvg)} tracking-tighter`}>
                                                                                    {teacherAvg.toFixed(1)}
                                                                                </h4>
                                                                                <span className="text-[10px] text-slate-300 font-bold">/5</span>
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                </>
                                                            );
                                                        })()}
                                                    </div>

                                                    <div className="space-y-6 pt-6 border-t border-slate-50">
                                                        <p className="text-[13px] font-black text-slate-800 uppercase tracking-widest px-1">累計成本分析</p>
                                                        <div className="space-y-5 px-1">
                                                            <div className="flex justify-between items-center">
                                                                <span className="text-[13px] font-bold text-slate-800 uppercase tracking-widest">模型花費</span>
                                                                <div className="flex items-center gap-2 text-amber-500">
                                                                    <GiTwoCoins size={18} />
                                                                    <span className="text-2xl font-black tracking-tighter">NT ${experimentStats.summarized_metrics?.total_cost_nt?.toFixed(1) || '0.0'}</span>
                                                                </div>
                                                            </div>
                                                            <div className="flex justify-between items-center">
                                                                <span className="text-[13px] font-bold text-slate-800 uppercase tracking-widest">碳足跡累計</span>
                                                                <div className="flex items-center gap-2 text-slate-700">
                                                                    <BiLeaf size={18} className="text-emerald-500" />
                                                                    <span className="text-2xl font-black tracking-tighter">{experimentStats.summarized_metrics?.total_carbon_g?.toFixed(2) || '0.00'} G</span>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Unified Timeline Chart (Full Width) */}
                                        <div className="bg-white p-8 rounded-[32px] border border-slate-100 shadow-sm flex flex-col relative min-h-[480px]">
                                            <div className="flex items-center justify-between mb-8 flex-wrap gap-3">
                                                {/* Left: Title + Legend */}
                                                <div className="flex items-center gap-6">
                                                    <h5 className="text-xl font-black text-slate-800">
                                                        教材歷程
                                                    </h5>
                                                    <div className="flex items-center gap-4 text-[10px] font-black uppercase tracking-wider text-slate-400 border-l border-slate-100 pl-6">
                                                        <div className="flex items-center gap-1" title="最終被教師點擊儲存並採用的教材"><div className="w-2.5 h-2.5 bg-emerald-400 rounded-full" /> 採用</div>
                                                        <div className="flex items-center gap-1" title="修改比例 > 50%，代表教師對 AI 產出的內容進行了大幅度的手動調整"><div className="w-2.5 h-2.5 bg-orange-400 rounded-full" /> 大量編修 (超過50%)</div>
                                                        <div className="flex items-center gap-1" title="教師曾進行編修，但最終選擇捨棄或未儲存該次生成結果"><div className="w-2.5 h-2.5 bg-red-400 rounded-full" /> 捨棄</div>
                                                        <div className="flex items-center gap-1" title="設定參數至生成前的耗時"><div className="w-2.5 h-2.5 bg-indigo-200 rounded-full" /> 設定時長</div>
                                                        <div className="flex items-center gap-1" title="生成後的手動編修與調整耗時"><div className="w-2.5 h-2.5 bg-slate-100 border border-slate-200 rounded-full" /> 編修時長</div>
                                                        <div className="flex items-center gap-1" title="紫色數字代表該教材在同一連續產出歷程 (Session) 中的調整次序"><div className="w-3.5 h-3.5 rounded-full border-2 border-indigo-400 flex items-center justify-center text-[7px] font-black text-indigo-500">#</div> 重新生成</div>
                                                        <div className="flex items-center gap-1" title="數字代表教師在編修過程中查看引註資料的次數"><div className="w-3.5 h-3.5 rounded-full border-2 border-sky-500 flex items-center justify-center text-[7px] font-black text-sky-600">#</div> 引用來源詳情</div>
                                                    </div>
                                                </div>
                                                {/* Right: Filters + Pagination */}
                                                <div className="flex items-center gap-3">
                                                    <div className="flex items-center gap-4 px-4 py-1.5 bg-slate-50 rounded-2xl border border-slate-100">
                                                        <label className="flex items-center gap-2 cursor-pointer select-none">
                                                            <input
                                                                type="checkbox"
                                                                checked={filterShortEdits}
                                                                onChange={(e) => {
                                                                    setFilterShortEdits(e.target.checked);
                                                                    setRq1PageIndex(0);
                                                                }}
                                                                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                                            />
                                                            <span className="text-[10px] font-black text-slate-500 uppercase tracking-wider">過濾測試資料 (30s)</span>
                                                        </label>
                                                        <label className="flex items-center gap-2 cursor-pointer select-none border-l border-slate-200 pl-4">
                                                            <input
                                                                type="checkbox"
                                                                checked={showSavedOnly}
                                                                onChange={(e) => {
                                                                    setShowSavedOnly(e.target.checked);
                                                                    setRq1PageIndex(0);
                                                                }}
                                                                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                                            />
                                                            <span className="text-[10px] font-black text-slate-500 uppercase tracking-wider">僅看已採用</span>
                                                        </label>
                                                    </div>
                                                    <button onClick={() => setRq1PageIndex(p => Math.max(0, p - 1))} disabled={rq1PageIndex === 0} className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30"><FiChevronLeft /></button>
                                                    <span className="text-xs font-black text-slate-400">PAGE {rq1PageIndex + 1}</span>
                                                    <button onClick={() => setRq1PageIndex(p => p + 1)} disabled={((experimentStats?.rq_metrics?.rq1?.edit_efficiency || []).filter((d: any) => (!showSavedOnly || d.is_saved) && (!filterShortEdits || ((d.edit_duration_seconds || 0) + (d.prep_stats?.prep_duration || 0)) >= 30)).length <= (rq1PageIndex + 1) * itemsPerPage)} className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-30"><FiChevronRight /></button>
                                                </div>
                                            </div>

                                            {(() => {
                                                const rawData = [...(experimentStats?.rq_metrics?.rq1?.edit_efficiency || [])]
                                                    .filter(d => !filterShortEdits || ((d.edit_duration_seconds || 0) + (d.prep_stats?.prep_duration || 0)) >= 30)
                                                    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
                                                const filteredData = showSavedOnly ? rawData.filter(d => d.is_saved) : rawData;
                                                const data = filteredData.slice(rq1PageIndex * itemsPerPage, (rq1PageIndex + 1) * itemsPerPage);

                                                const maxDuration = Math.max(...data.map(d => Math.min((d.edit_duration_seconds || 0) + (d.prep_stats?.prep_duration || 0), 900)), 1) || 60;

                                                return (
                                                    <div className="flex-1 flex flex-col gap-6 relative">
                                                        {data.length === 0 ? (
                                                            <div className="flex-1 flex flex-col items-center justify-center py-20 text-slate-300 gap-4">
                                                                <BsClipboardDataFill size={48} className="opacity-20" />
                                                                <div className="text-center">
                                                                    <p className="font-bold text-slate-400">目前暫無發展軌跡數據</p>
                                                                    <p className="text-xs text-slate-300 mt-1">請嘗試縮小篩選範圍或選擇特定課程單元</p>
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <>
                                                                <div className="flex-1 h-[260px] relative ml-20">
                                                                    {/* Y-Axis Labels */}
                                                                    <div className="absolute -left-20 top-0 bottom-0 w-20 text-[10px] font-black text-slate-900 uppercase">
                                                                        <div className="absolute top-0 right-4 flex flex-col items-end whitespace-nowrap">
                                                                            <span>編修幅度</span>
                                                                            <span>50%</span>
                                                                        </div>
                                                                        <div className="absolute top-1/2 -translate-y-1/2 right-0 flex items-center gap-1 text-slate-900 font-bold whitespace-nowrap">
                                                                            <span>0</span>
                                                                            <div className="w-14 border-t border-slate-300" />
                                                                        </div>
                                                                        <div className="absolute bottom-0 right-4 flex flex-col items-end whitespace-nowrap">
                                                                            <span>教材總投入時長</span>
                                                                            <span>{maxDuration > 60 ? `${Math.floor(maxDuration / 60)}M ${Math.round(maxDuration % 60)}S` : `${Math.round(maxDuration)}S`}</span>
                                                                        </div>
                                                                    </div>

                                                                    {/* Baseline (Exact Center) */}
                                                                    <div className="absolute top-1/2 left-0 right-0 border-t-2 border-slate-100/80 z-10 -translate-y-1/2" />

                                                                    <div className="w-full h-full flex items-stretch gap-1.5 px-[1px]">
                                                                        {data.map((item: any, i: number) => {
                                                                            const threshold = 0.5;
                                                                            const visualRatio = (item.edit_ratio > 0 && item.edit_ratio < 0.01) ? 0.02 : item.edit_ratio;
                                                                            const ratioH = visualRatio > 0 ? Math.min((visualRatio / threshold) * 100, 100) : 0;
                                                                            const isHighEffort = item.edit_ratio > threshold;

                                                                            return (
                                                                                <button
                                                                                    key={i}
                                                                                    type="button"
                                                                                    className="flex-1 group cursor-pointer relative border-none bg-transparent p-0 outline-none"
                                                                                    onClick={(e) => {
                                                                                        e.preventDefault();
                                                                                        e.stopPropagation();
                                                                                        setSelectedGeneration(item);
                                                                                        setIsDetailModalOpen(true);
                                                                                    }}
                                                                                >
                                                                                    {/* Upper Bar (Ratio) */}
                                                                                    <div className="absolute bottom-1/2 left-0 right-0 h-1/2 flex flex-col justify-end">
                                                                                        <div
                                                                                            className={`w-full rounded-t-lg transition-all transform group-hover:scale-x-110 shadow-sm ${item.is_saved ? (isHighEffort ? 'bg-orange-400' : 'bg-emerald-400') : (item.edit_ratio > 0 ? 'bg-red-400' : 'bg-slate-100')}`}
                                                                                            style={{ height: `${ratioH}%`, minHeight: item.edit_ratio > 0 ? '2px' : '0px' }}
                                                                                        />
                                                                                    </div>

                                                                                    {/* Lower Bar (Total Duration: Setting + Editing) */}
                                                                                    {(() => {
                                                                                        const rawSetting = item.prep_stats?.prep_duration || 0;
                                                                                        const rawEditing = item.edit_duration_seconds || 0;

                                                                                        // Visual capping at 15 mins
                                                                                        const tSetting = Math.min(rawSetting, 900);
                                                                                        const tEditing = Math.min(rawEditing, 900);
                                                                                        const tTotalDisplay = Math.min(rawSetting + rawEditing, 900);

                                                                                        if (tTotalDisplay > 0) {
                                                                                            return (
                                                                                                <div
                                                                                                    className="absolute top-1/2 left-0 right-0 pt-0.5 flex flex-col items-stretch overflow-hidden"
                                                                                                    style={{ height: `${Math.min((tTotalDisplay / maxDuration) * 50, 50)}%` }}
                                                                                                >
                                                                                                    {/* Setting Duration (T_setting) */}
                                                                                                    <div
                                                                                                        className="w-full bg-indigo-200 group-hover:bg-indigo-300 transition-all"
                                                                                                        style={{ height: `${(tSetting / (tSetting + tEditing)) * 100}%` }}
                                                                                                    />
                                                                                                    {/* Editing Duration (T_editing) */}
                                                                                                    <div
                                                                                                        className="w-full flex-1 bg-slate-100 group-hover:bg-slate-200 transition-all border-x border-b border-slate-200/20"
                                                                                                    />
                                                                                                </div>
                                                                                            );
                                                                                        }
                                                                                        return null;
                                                                                    })()}

                                                                                    {/* Hover Tooltip Peek */}
                                                                                    <div className="absolute -top-14 left-1/2 -translate-x-1/2 bg-slate-900/95 backdrop-blur-md text-white text-[10px] px-3 py-2 rounded-xl opacity-0 group-hover:opacity-100 pointer-events-none z-30 whitespace-nowrap shadow-2xl border border-white/10 flex flex-col gap-1">
                                                                                        <div className="flex justify-between gap-4 font-black">
                                                                                            <span>編修幅度 (Edit Ratio):</span>
                                                                                            <span className="text-orange-400">{(item.edit_ratio * 100).toFixed(1)}%</span>
                                                                                        </div>
                                                                                        <div className="flex justify-between gap-4">
                                                                                            <span className="text-slate-400">設定時長 (T_setting):</span>
                                                                                            <span className="font-bold">{(item.prep_stats?.prep_duration || 0).toFixed(0)}s</span>
                                                                                        </div>
                                                                                        <div className="flex justify-between gap-4">
                                                                                            <span className="text-slate-400">編修時長 (T_edit):</span>
                                                                                            <span className="font-bold">{(item.edit_duration_seconds || 0).toFixed(0)}s</span>
                                                                                        </div>
                                                                                        <div className="border-t border-white/10 mt-1 pt-1 flex justify-between gap-4 text-white font-black text-[11px]">
                                                                                            <span>總投入時長 (T_total):</span>
                                                                                            <span>{((item.edit_duration_seconds || 0) + (item.prep_stats?.prep_duration || 0)) > 60 ? `${Math.floor(((item.edit_duration_seconds || 0) + (item.prep_stats?.prep_duration || 0)) / 60)}m ${Math.round(((item.edit_duration_seconds || 0) + (item.prep_stats?.prep_duration || 0)) % 60)}s` : `${Math.round((item.edit_duration_seconds || 0) + (item.prep_stats?.prep_duration || 0))}s`}</span>
                                                                                        </div>
                                                                                    </div>

                                                                                    {/* Markers */}
                                                                                    {item.source_preview_count > 0 && (
                                                                                        <div className="absolute top-1/2 left-[calc(50%+10px)] -translate-x-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-white border-2 border-sky-500 flex items-center justify-center text-[8px] font-black text-sky-600 z-20 shadow-sm">
                                                                                            {item.source_preview_count}
                                                                                        </div>
                                                                                    )}

                                                                                    {(() => {
                                                                                        const allGens = experimentStats?.rq_metrics?.rq1?.edit_efficiency || [];
                                                                                        const sessionRounds = allGens.filter((g: any) =>
                                                                                            (g.course_content_id === item.course_content_id && g.course_content_id != null) ||
                                                                                            (g.session_id === item.session_id && g.session_id != null) ||
                                                                                            (g.job_id === item.job_id)
                                                                                        ).sort((a: any, b: any) =>
                                                                                            (a.regen_index || 0) - (b.regen_index || 0) ||
                                                                                            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
                                                                                        );

                                                                                        if (sessionRounds.length > 1) {
                                                                                            const iterIndex = sessionRounds.findIndex((r: any) =>
                                                                                                (r.id != null && r.id === item.id) ||
                                                                                                (r.generated_content_id != null && r.generated_content_id === item.generated_content_id) ||
                                                                                                (r.created_at != null && r.created_at === item.created_at)
                                                                                            ) + 1;
                                                                                            return (
                                                                                                <div className="absolute top-1/2 left-[calc(50%-10px)] -translate-x-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-white border-2 border-indigo-400 flex items-center justify-center text-[8px] font-black text-indigo-500 z-20 shadow-sm">
                                                                                                    {iterIndex}
                                                                                                </div>
                                                                                            );
                                                                                        }
                                                                                        return null;
                                                                                    })()}
                                                                                </button>
                                                                            );
                                                                        })}
                                                                    </div>
                                                                </div>

                                                                {/* Labels */}
                                                                <div className="flex items-start ml-20 gap-1.5 h-20">
                                                                    {data.map((item: any, i: number) => (
                                                                        <button
                                                                            key={i}
                                                                            type="button"
                                                                            className="flex-1 flex flex-col items-center gap-1 min-w-0 relative cursor-pointer group/label border-none bg-transparent p-0 outline-none"
                                                                            onClick={(e) => {
                                                                                e.preventDefault();
                                                                                e.stopPropagation();
                                                                                setSelectedGeneration(item);
                                                                                setIsDetailModalOpen(true);
                                                                            }}>
                                                                            <div className={`w-2 h-2 rounded-full mb-1 transition-transform group-hover/label:scale-125 ${item.is_saved ? 'bg-emerald-500' : 'bg-slate-200'}`} />
                                                                            <div className="text-[10px] font-bold text-slate-500 text-center leading-[1.3] max-h-12 overflow-hidden break-words w-full px-1 group-hover/label:text-blue-600 transition-colors" title={item.title}>
                                                                                <span className="text-[7.5px] bg-indigo-50 px-1 py-0.5 rounded text-indigo-500 border border-indigo-100/50 mr-1 align-middle uppercase font-black">
                                                                                    {item.content_tag || '生成內容'}
                                                                                </span>
                                                                                <span className="align-middle">
                                                                                    {item.title || '無標題'}
                                                                                </span>
                                                                                <span className="text-[8px] text-slate-300 font-black uppercase tracking-tighter ml-1 align-middle">
                                                                                    {item.created_at ? new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'N/A'}
                                                                                </span>
                                                                            </div>
                                                                        </button>
                                                                    ))}
                                                                </div>
                                                            </>
                                                        )}
                                                    </div>
                                                );
                                            })()}
                                        </div>

                                    </div>
                                </div>

                                {/* 4. Student Behavior Analysis Section */}
                                <div className="space-y-6">
                                    <h4 className="flex items-center gap-3 text-2xl font-black text-slate-800">
                                        <span className="w-2 h-8 bg-emerald-600 rounded-full shadow-lg shadow-emerald-100" />
                                        學生行為分析 (Student Behavior Analysis)
                                    </h4>

                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                                        <div className="bg-white p-7 rounded-[28px] border border-slate-100 shadow-sm group hover:border-emerald-200 transition-all">
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">錯誤後回看率</p>
                                            <h4 className="text-3xl font-black text-emerald-600 group-hover:scale-105 transition-transform origin-left">{((experimentStats.rq_metrics?.rq3?.remedial_rate || 0) * 100).toFixed(1)}%</h4>
                                            <p className="text-[10px] text-slate-400 mt-3 font-medium">答錯後主動點擊教材複習比例</p>
                                        </div>
                                        <div className="bg-white p-7 rounded-[28px] border border-slate-100 shadow-sm group hover:border-blue-200 transition-all">
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">首答正確率</p>
                                            <h4 className="text-3xl font-black text-slate-800 group-hover:scale-105 transition-transform origin-left">{((experimentStats.student_stats?.correctness_rate || 0) * 100).toFixed(1)}%</h4>
                                            <p className="text-[10px] text-slate-400 mt-3 font-medium">目前篩選範圍內首答正確比例</p>
                                        </div>
                                        <div className="bg-white p-7 rounded-[28px] border border-slate-100 shadow-sm group hover:border-blue-200 transition-all">
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">平均閱讀深度</p>
                                            <h4 className="text-3xl font-black text-slate-800 group-hover:scale-105 transition-transform origin-left">{((experimentStats.student_stats?.avg_scroll_depth || 0) * 100).toFixed(0)}%</h4>
                                            <p className="text-[10px] text-slate-400 mt-3 font-medium">學生對教材內容的平均覆蓋度</p>
                                        </div>
                                        <div className="bg-white p-7 rounded-[28px] border border-slate-100 shadow-sm group hover:border-indigo-200 transition-all">
                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">平均閱讀時長</p>
                                            <h4 className="text-3xl font-black text-indigo-600 group-hover:scale-105 transition-transform origin-left">{((experimentStats.student_stats?.avg_reading_time || 0) / 60).toFixed(1)} min</h4>
                                            <p className="text-[10px] text-slate-400 mt-3 font-medium">單個單元之持續專注時長估算</p>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                                        <div className="bg-white p-8 rounded-[40px] border border-slate-100 shadow-sm flex flex-col items-center justify-center py-16">
                                            <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-8 text-center w-full">引用溯源互動次數 (Citation Interactions)</h5>
                                            <div className="text-7xl font-black text-indigo-600 mb-4 drop-shadow-sm">{experimentStats.rq_metrics?.rq4?.citation_trust ?? 0}</div>
                                            <p className="text-[10px] text-slate-400 font-bold uppercase tracking-widest mb-4">Total Interactions</p>
                                            <p className="text-xs text-slate-300 italic text-center max-w-xs">反映學生對「AI 生成內容必須可被校驗」的需求強度</p>
                                        </div>
                                        <div className="bg-white p-8 rounded-[40px] border border-slate-100 shadow-sm flex flex-col">
                                            <h5 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-8">離場導航行為分析 (Exit Navigation)</h5>
                                            <div className="space-y-5 flex-1 justify-center flex flex-col">
                                                {Object.entries(experimentStats.rq_metrics?.rq4?.nav_usage || {}).map(([key, val]: [string, any]) => (
                                                    <div key={key} className="space-y-2">
                                                        <div className="flex justify-between text-[10px] font-black uppercase tracking-widest">
                                                            <span className="text-slate-500">{key === 'back' ? 'BACK_TO_COURSE' : key === 'next' ? 'NEXT_ITEM' : key}</span>
                                                            <span className="text-slate-900">{val} TIMES</span>
                                                        </div>
                                                        <div className="w-full h-2.5 bg-slate-50 rounded-full overflow-hidden border border-slate-100/50">
                                                            <div className="h-full bg-blue-500 rounded-full" style={{ width: `${(val / ((Object.values(experimentStats.rq_metrics?.rq4?.nav_usage || {}).reduce((a: any, b: any) => a + b, 0) as number) || 1)) * 100}%` }} />
                                                        </div>
                                                    </div>
                                                ))}
                                                {Object.keys(experimentStats.rq_metrics?.rq4?.nav_usage || {}).length === 0 && <div className="text-center text-slate-300 italic py-10">暫無導航紀錄</div>}
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* 5. SRL Behavior Analysis Section (Restored & Optimized) */}
                                <div className="space-y-4 mt-2 mb-2 py-4 border-t border-b border-slate-100">
                                    <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
                                        <div className="space-y-1">
                                            <h4 className="flex items-center gap-3 text-3xl font-black text-slate-800">
                                                <span className="w-2.5 h-10 bg-indigo-600 rounded-full shadow-lg shadow-indigo-100" />
                                                SRL 自我調整學習行為分析
                                            </h4>
                                            <p className="text-sm font-bold text-slate-400 ml-5">基於 Self-Regulated Learning 理論的五維度學習參與度建模 (LEI)</p>
                                        </div>
                                        <div className="flex items-center gap-2 px-4 py-2 bg-indigo-50 text-indigo-600 rounded-2xl text-xs font-black border border-indigo-100">
                                            <FiInfo size={14} />
                                            無前後測課程之替代性教學成效指標
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                                        {/* Row 1 Left: LEI Overview Card */}
                                        <div className="lg:col-span-1 bg-gradient-to-br from-indigo-600 to-blue-700 p-8 rounded-[40px] text-white shadow-xl shadow-indigo-100 relative overflow-hidden group min-h-[320px]">
                                            <div className="absolute -top-12 -right-12 p-12 opacity-10 rotate-12 group-hover:rotate-0 transition-transform duration-1000">
                                                <FiActivity size={200} />
                                            </div>
                                            <div className="relative z-10 h-full flex flex-col">
                                                <p className="text-[10px] font-black uppercase tracking-[0.2em] opacity-80 mb-6">Learning Engagement Index</p>
                                                <div className="flex-1 flex flex-col justify-center items-center py-6">
                                                    <h2 className="text-7xl font-black mb-2 leading-none">{(experimentStats?.rq_metrics?.srl_analysis?.overall_lei || 0).toFixed(0)}</h2>
                                                    <p className="text-xs font-bold opacity-60 uppercase tracking-widest">整體平均參與度</p>
                                                </div>
                                                <div className="mt-8 pt-8 border-t border-white/10 space-y-4">
                                                    <div className="flex justify-between items-center text-[10px] font-black uppercase tracking-widest opacity-80">
                                                        <span>Quartile P25-P75</span>
                                                        <span>{((experimentStats?.rq_metrics?.srl_analysis?.lei_quartiles?.p25 || 0)).toFixed(0)} - {((experimentStats?.rq_metrics?.srl_analysis?.lei_quartiles?.p75 || 0)).toFixed(0)}</span>
                                                    </div>
                                                    <div className="w-full h-1.5 bg-white/20 rounded-full overflow-hidden">
                                                        <div
                                                            className="h-full bg-amber-600 rounded-full"
                                                            style={{
                                                                marginLeft: `${(experimentStats?.rq_metrics?.srl_analysis?.lei_quartiles?.p25 || 0)}%`,
                                                                width: `${(experimentStats?.rq_metrics?.srl_analysis?.lei_quartiles?.p75 || 0) - (experimentStats?.rq_metrics?.srl_analysis?.lei_quartiles?.p25 || 0)}%`
                                                            }}
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Row 1 Middle: LEI Distribution Histogram */}
                                        <div className="lg:col-span-2 bg-white p-8 rounded-[40px] border border-slate-100 shadow-sm flex flex-col">
                                            <h5 className="text-[11px] font-black text-slate-400 uppercase tracking-widest mb-8 flex items-center gap-2">
                                                <FiBarChart2 className="text-indigo-500" /> 學生參與度分佈 (LEI Score Distribution)
                                            </h5>
                                            <div className="flex-1 flex items-end gap-1 px-4 border-b border-l border-slate-100 pb-2 mb-1">
                                                {(() => {
                                                    const bins = Array(10).fill(0);
                                                    const dist = experimentStats?.rq_metrics?.srl_analysis?.lei_distribution || [];
                                                    dist.forEach((r: any) => {
                                                        const idx = Math.min(9, Math.floor((r.lei_score || 0) / 10));
                                                        bins[idx]++;
                                                    });
                                                    const maxCount = Math.max(...bins) || 1;
                                                    return bins.map((count, i) => (
                                                        <div key={i} className="flex-1 group relative h-full flex flex-col justify-end">
                                                            <div
                                                                className="w-full bg-indigo-50 rounded-t-lg transition-all hover:bg-indigo-500 hover:shadow-lg hover:shadow-indigo-100 min-h-[4px]"
                                                                style={{ height: `${(count / maxCount) * 100}%` }}
                                                            />
                                                            <div className="absolute -top-12 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] px-3 py-1.5 rounded-lg opacity-0 group-hover:opacity-100 shadow-xl pointer-events-none z-10 whitespace-nowrap transition-all scale-90 group-hover:scale-100">
                                                                {i * 10}-{(i + 1) * 10}: {count} 名學生
                                                            </div>
                                                        </div>
                                                    ));
                                                })()}
                                            </div>
                                        </div>

                                        {/* Row 1 Far Right: Student Inquiry KP Alignment */}
                                        <div className="lg:col-span-1 bg-white p-8 rounded-[40px] border border-slate-100 shadow-sm flex flex-col">
                                            <h5 className="text-[11px] font-black text-slate-400 uppercase tracking-widest mb-6 flex items-center gap-2">
                                                <FiZap className="text-amber-500" /> 知識點提問觸發 (Student KP Inquiry)
                                            </h5>
                                            <div className="flex-1 space-y-4 overflow-y-auto pr-2 max-h-[200px] custom-scrollbar">
                                                {(experimentStats.rq_metrics?.srl_analysis?.kp_alignment || []).length > 0 ? (
                                                    experimentStats.rq_metrics.srl_analysis.kp_alignment
                                                        .sort((a: any, b: any) => b.student_inquiry_count - a.student_inquiry_count)
                                                        .slice(0, 8)
                                                        .map((kp: any, idx: number) => {
                                                            const maxInquiry = Math.max(...experimentStats.rq_metrics.srl_analysis.kp_alignment.map((k: any) => k.student_inquiry_count)) || 1;
                                                            const pct = (kp.student_inquiry_count / maxInquiry) * 100;
                                                            return (
                                                                <div key={idx} className="space-y-1.5">
                                                                    <div className="flex justify-between items-center text-[10px] font-bold">
                                                                        <span className="text-slate-600 truncate w-2/3">{kp.kp_name}</span>
                                                                        <span className="text-amber-600">{kp.student_inquiry_count} 次</span>
                                                                    </div>
                                                                    <div className="w-full h-1.5 bg-slate-50 rounded-full overflow-hidden">
                                                                        <div className="h-full bg-amber-600 rounded-full" style={{ width: `${pct}%` }} />
                                                                    </div>
                                                                </div>
                                                            );
                                                        })
                                                ) : (
                                                    <div className="h-full flex items-center justify-center text-[10px] text-slate-300 italic">暫無觸發數據</div>
                                                )}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Row 2: Dimension Breakdown (Scatter Plots) - Matching Visual Representation */}
                                    <div className="bg-white p-6 rounded-[40px] border border-slate-100 shadow-sm space-y-4">
                                        <div className="flex items-center justify-between">
                                            <h5 className="text-sm font-black text-slate-800 flex items-center gap-2">
                                                <FiActivity className="text-blue-500" />
                                                個體行為散點分析 (Individual SRL Behavior Scatters)
                                            </h5>
                                            <p className="text-[10px] font-bold text-slate-400 italic">點擊圓點可查看詳細數據 • 軸線代表該維度之原始特徵值</p>
                                        </div>

                                        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-8">
                                            {[
                                                { key: 'reading', label: '有效閱讀', icon: FiEye, xKey: 'T', yKey: 'D', xLabel: '時長 (Time)', yLabel: '深度 (Depth)', xUnit: '秒', yUnit: '%' },
                                                { key: 'tracing', label: '資訊溯源', icon: FiSearch, xKey: 'C', yKey: 'lei_score', xLabel: '點擊 (Click)', yLabel: '參與度 (LEI)', xUnit: '次', yUnit: '分' },
                                                { key: 'inquiry', label: '深度提問', icon: FiMessageSquare, xKey: 'M_count', yKey: 'M_kp_depth', xLabel: '次數 (Count)', yLabel: 'KP 深度 (KP)', xUnit: '次', yUnit: '個' },
                                                { key: 'testing', label: '自我檢測', icon: FiCheck, xKey: 'question_count', yKey: 'A', xLabel: '題數 (Quest)', yLabel: '正確率 (Acc)', xUnit: '題', yUnit: '%' },
                                                { key: 'remedial', label: '補救循環', icon: FiRefreshCw, xKey: 'R', yKey: 'lei_score', xLabel: '次數 (Count)', yLabel: '參與度 (LEI)', xUnit: '次', yUnit: '分' },
                                            ].map((dim) => {
                                                const students = experimentStats?.rq_metrics?.srl_analysis?.lei_distribution || [];
                                                const getVal = (s: any, key: string) => key === 'lei_score' ? s.lei_score : (s.metrics?.[key] ?? 0);

                                                const xVals = students.map((s: any) => getVal(s, dim.xKey));
                                                const yVals = students.map((s: any) => getVal(s, dim.yKey));
                                                const maxX = Math.max(...xVals, 1);
                                                const maxY = Math.max(...yVals, 1);

                                                return (
                                                    <div key={dim.key} className="flex flex-col h-full group pt-4">
                                                        <div className="flex-1 min-h-[200px] bg-slate-50/30 rounded-[32px] relative p-4 border border-slate-100 group-hover:bg-white group-hover:border-blue-100 group-hover:shadow-xl group-hover:shadow-blue-50/50 transition-all duration-500">
                                                            {/* X/Y Axes Labels - Moved completely outside plotting area */}
                                                            <div className="absolute -top-5 left-4 text-[10px] font-black text-slate-800 uppercase tracking-tighter bg-white shadow-md px-3 py-1 rounded-full border border-slate-100 z-20 group-hover:text-blue-600 group-hover:border-blue-200 transition-all">
                                                                {dim.yLabel}
                                                            </div>
                                                            <div className="absolute -bottom-3 right-4 text-[10px] font-black text-slate-800 uppercase tracking-tighter bg-white shadow-md px-3 py-1 rounded-full border border-slate-100 z-20 group-hover:text-blue-600 group-hover:border-blue-200 transition-all">
                                                                {dim.xLabel}
                                                            </div>

                                                            <svg className="w-full h-full" viewBox="0 0 100 100" preserveAspectRatio="none">
                                                                {[0, 25, 50, 75, 100].map(v => (
                                                                    <line key={`h-${v}`} x1="0" y1={v} x2="100" y2={v} stroke="#f1f5f9" strokeWidth="0.5" />
                                                                ))}
                                                                {[0, 25, 50, 75, 100].map(v => (
                                                                    <line key={`v-${v}`} x1={v} y1="0" x2={v} y2="100" stroke="#f1f5f9" strokeWidth="0.5" />
                                                                ))}
                                                                {(() => {
                                                                    const groupedMap = new Map();
                                                                    students.forEach((s: any) => {
                                                                        const rawX = getVal(s, dim.xKey);
                                                                        const rawY = getVal(s, dim.yKey);
                                                                        const coordKey = `${rawX}_${rawY}`;
                                                                        if (!groupedMap.has(coordKey)) groupedMap.set(coordKey, { rawX, rawY, list: [] });
                                                                        groupedMap.get(coordKey).list.push(s);
                                                                    });

                                                                    return Array.from(groupedMap.values()).map((group: any, gIdx: number) => {
                                                                        const { rawX, rawY, list } = group;
                                                                        const seed = Math.abs(rawX * 133.31 + rawY * 77.7);
                                                                        const jitterX = (Math.sin(seed) * 1.5);
                                                                        const jitterY = (Math.cos(seed * 0.9) * 1.5);

                                                                        const useRootX = dim.xKey === 'T';
                                                                        const scaledX = useRootX ? Math.sqrt(rawX) : rawX;
                                                                        const scaledMaxX = useRootX ? Math.sqrt(maxX || 1) : (maxX || 1);

                                                                        const x = 5 + (scaledX / (scaledMaxX || 1)) * 90 + jitterX;
                                                                        const y = 95 - (rawY / (maxY || 1)) * 90 + jitterY;

                                                                        const isZero = rawX === 0 && rawY === 0;
                                                                        const baseOpacity = isZero ? 0.1 : 0.45;
                                                                        const opacity = Math.min(baseOpacity + (list.length - 1) * 0.25, 1.0);
                                                                        const radius = isZero ? 1.5 : (5 + Math.min(list.length - 1, 3) * 0.5);
                                                                        const isActive = srlTooltip?.students === list;

                                                                        return (
                                                                            <circle
                                                                                key={gIdx}
                                                                                cx={x} cy={y} r={isActive && srlTooltip?.isLocked ? radius * 1.5 : radius}
                                                                                className={`
                                                                                ${isZero ? 'fill-slate-200' : 'fill-blue-500'} 
                                                                                hover:fill-blue-400 
                                                                                transition-all duration-300 cursor-pointer
                                                                                ${isActive && srlTooltip?.isLocked ? 'stroke-white stroke-[0.5px]' : ''}
                                                                            `}
                                                                                style={{ opacity: isActive && srlTooltip?.isLocked ? 1 : opacity }}
                                                                                onMouseEnter={(e: any) => {
                                                                                    if (!srlTooltip?.isLocked) {
                                                                                        const rect = e.currentTarget.getBoundingClientRect();
                                                                                        setSrlTooltip({ x: rect.left + rect.width / 2, y: rect.top, students: list, dim: dim, isLocked: false });
                                                                                    }
                                                                                }}
                                                                                onMouseLeave={() => {
                                                                                    if (!srlTooltip?.isLocked) {
                                                                                        setSrlTooltip(null);
                                                                                    }
                                                                                }}
                                                                                onClick={(e) => {
                                                                                    e.stopPropagation();
                                                                                    const rect = e.currentTarget.getBoundingClientRect();
                                                                                    setSrlTooltip({
                                                                                        x: rect.left + rect.width / 2,
                                                                                        y: rect.top,
                                                                                        students: list,
                                                                                        dim: dim,
                                                                                        isLocked: true
                                                                                    });
                                                                                }}
                                                                            />
                                                                        );
                                                                    });
                                                                })()}
                                                            </svg>
                                                        </div>
                                                        <div className="mt-4 flex items-center gap-3 px-2">
                                                            <div className={`w-8 h-8 rounded-[12px] bg-slate-50 text-slate-400 flex items-center justify-center group-hover:bg-blue-500 group-hover:text-white group-hover:shadow-xl group-hover:shadow-blue-100 transition-all duration-300`}>
                                                                <dim.icon size={16} />
                                                            </div>
                                                            <div className="flex flex-col">
                                                                <h6 className="text-[16px] font-black text-slate-700 tracking-[0.05em] leading-tight">{dim.label}</h6>
                                                                <p className="text-[12px] text-slate-400 font-bold mt-0.5 leading-tight">個體分佈概況</p>
                                                            </div>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </div>
                                </div>

                                {/* 5. Usage Activity Trends - MOVED TO BOTTOM */}
                                <div className="bg-white p-8 rounded-[40px] border border-slate-100 shadow-sm mt-10">
                                    <h4 className="text-lg font-extrabold text-slate-800 mb-8 flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <GiArchiveResearch className="text-purple-500" size={24} />
                                            教師/學生雙端系統使用狀況 (近15天)
                                        </div>
                                        <div className="flex gap-4 text-[10px] uppercase font-black tracking-widest text-slate-900">
                                            <div className="flex items-center gap-1.5"><span className="w-3 h-3 bg-blue-500 rounded-full" /> 教師內容生產</div>
                                            <div className="flex items-center gap-1.5"><span className="w-3 h-3 bg-emerald-500 rounded-full" /> 學生答題互動</div>
                                        </div>
                                    </h4>
                                    <div className="h-[180px] flex items-end gap-2 px-4 border-l border-b border-slate-200">
                                        {(experimentStats.daily_stats || []).map((day: any, i: number) => {
                                            const max = Math.max(...(experimentStats.daily_stats || []).map((d: any) => (d.t_actions || 0) + (d.s_actions || 0))) || 1;
                                            return (
                                                <div key={i} className="flex-1 flex flex-col justify-end gap-0.5 group relative h-full">
                                                    <div className="w-full bg-blue-500/80 rounded-t-sm transition-all hover:bg-blue-600" style={{ height: `${((day.t_actions || 0) / max) * 100}%` }} />
                                                    <div className="w-full bg-emerald-500/80 rounded-t-sm transition-all hover:bg-emerald-600" style={{ height: `${((day.s_actions || 0) / max) * 100}%` }} />
                                                    <div className="absolute -top-12 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 pointer-events-none z-30 whitespace-nowrap text-center shadow-xl">
                                                        {day.date}<br />
                                                        T: {day.t_actions} | S: {day.s_actions}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                    <div className="flex justify-between mt-2 px-1 text-[10px] text-slate-400 font-bold">
                                        <span>15 Days Ago</span>
                                        <span>Today</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'users' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                            <div className="bg-white p-6 rounded-[32px] shadow-sm border border-slate-100 mb-8">
                                <div className="flex gap-4">
                                    <div className="relative flex-1">
                                        <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none text-slate-400">
                                            <FiSearch />
                                        </div>
                                        <input
                                            type="text"
                                            value={searchKeyword}
                                            onChange={(e) => setSearchKeyword(e.target.value)}
                                            onKeyDown={(e) => e.key === 'Enter' && handleSearchUsers()}
                                            placeholder="請輸入姓名或 Email 進行搜尋..."
                                            className="w-full pl-11 pr-4 py-3.5 bg-slate-50 border-2 border-transparent focus:border-blue-400 focus:bg-white rounded-2xl outline-none transition-all font-medium"
                                        />
                                    </div>
                                    <button
                                        onClick={handleSearchUsers}
                                        disabled={isSearching}
                                        className="px-8 bg-blue-600 text-white font-bold rounded-2xl hover:bg-blue-700 transition-all shadow-lg shadow-blue-100 disabled:opacity-50"
                                    >
                                        {isSearching ? '搜尋中...' : '搜尋'}
                                    </button>
                                </div>
                            </div>

                            <div className="grid gap-4">
                                {searchResults.length > 0 ? (
                                    searchResults.map(u => (
                                        <div key={u.id} className="bg-white p-6 rounded-3xl border border-slate-100 flex items-center justify-between group hover:shadow-md transition-all">
                                            <div className="flex items-center gap-5">
                                                <div className="w-12 h-12 rounded-2xl bg-slate-50 flex items-center justify-center text-slate-400 font-bold text-lg">
                                                    {u.full_name?.charAt(0) || '?'}
                                                </div>
                                                <div>
                                                    <div className="flex items-center gap-2 mb-0.5">
                                                        <h4 className="font-bold text-slate-800">{u.full_name}</h4>
                                                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-widest ${u.role === 'admin' ? 'bg-indigo-600 text-white' :
                                                            u.role === 'teacher' ? 'bg-orange-100 text-orange-600' :
                                                                u.role === 'assistant' ? 'bg-purple-100 text-purple-600' :
                                                                    u.role === 'student' ? 'bg-blue-100 text-blue-600' :
                                                                        'bg-slate-100 text-slate-500'
                                                            }`}>
                                                            {u.role}
                                                        </span>
                                                    </div>
                                                    <p className="text-sm text-slate-400 font-medium">{u.email}</p>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-3">
                                                <button
                                                    onClick={() => fetchUserStats(u)}
                                                    className="px-4 py-2 text-slate-500 font-bold hover:bg-slate-100 rounded-xl transition-colors"
                                                >
                                                    管理數據
                                                </button>
                                            </div>
                                        </div>
                                    ))
                                ) : searchKeyword && !isSearching ? (
                                    <div className="text-center py-20 text-slate-400">
                                        <FiUser className="mx-auto mb-4 opacity-20" size={48} />
                                        <p className="font-medium">找不到符合條件的使用者</p>
                                    </div>
                                ) : (
                                    <div className="text-center py-20 text-slate-300 border-2 border-dashed border-slate-100 rounded-[40px]">
                                        <p className="font-bold">請輸入關鍵字搜尋使用者</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    )
                    }



                    <Modal
                        isOpen={!!statsUser}
                        onClose={() => !isDeleting && setStatsUser(null)}
                        title="使用者關聯資料統計"
                        maxWidth="max-w-xl"
                    >
                        {statsUser && (
                            <div className="space-y-6">
                                <div className="flex items-center gap-4 p-4 bg-slate-50 rounded-2xl border border-slate-100">
                                    <div className="w-12 h-12 rounded-2xl bg-white flex items-center justify-center text-slate-400 shadow-sm">
                                        <FiUser size={24} />
                                    </div>
                                    <div className="min-w-0">
                                        <h3 className="text-xl font-bold text-slate-800">{statsUser.full_name}</h3>
                                        <p className="text-sm text-slate-400 font-medium truncate">{statsUser.email}</p>
                                    </div>
                                </div>

                                <div>
                                    <h4 className="flex items-center gap-2 text-slate-800 font-bold mb-6">
                                        <span className="w-1.5 h-6 bg-blue-500 rounded-full" />
                                        關聯資料統計
                                    </h4>

                                    {!userStats ? (
                                        <div className="flex flex-col items-center justify-center py-12 gap-3 text-slate-400">
                                            <FiRefreshCw className="animate-spin" size={32} />
                                            <p className="text-sm font-medium">正在計算檔案與紀錄筆數...</p>
                                        </div>
                                    ) : (
                                        <div className="space-y-4">
                                            {userStats.stats && userStats.stats.length > 0 ? (
                                                <div className="grid grid-cols-1 gap-3">
                                                    {userStats.stats.map((s: any) => (
                                                        <div key={s.table} className="bg-slate-50 p-4 rounded-2xl flex items-center justify-between">
                                                            <span className="text-slate-500 font-bold text-sm tracking-wide">{s.table}</span>
                                                            <span className="bg-white px-3 py-1 rounded-xl text-blue-600 font-black text-sm shadow-sm">{s.count} 筆</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            ) : (
                                                <div className="bg-green-50 text-green-600 p-6 rounded-3xl text-center border border-green-100">
                                                    <p className="font-bold">此使用者目前沒有任何關聯資料筆數。</p>
                                                </div>
                                            )}

                                            <div className="mt-8 p-6 bg-red-50 rounded-3xl border border-red-100">
                                                <div className="flex items-start gap-4 text-red-600">
                                                    <div className="mt-1 flex-shrink-0"><FiShield size={20} /></div>
                                                    <div>
                                                        <h5 className="font-bold mb-1">危險動作警告</h5>
                                                        <p className="text-sm font-medium opacity-80 leading-relaxed">
                                                            點擊「刪除」將會徹底移除此使用者的帳號標籤，以及上述列出的所有課程、測驗、作答紀錄與各項偏好設定。此動作完全不可復原。
                                                        </p>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <div className="flex gap-4 pt-4 border-t border-slate-50">
                                    <button
                                        onClick={() => setStatsUser(null)}
                                        disabled={isDeleting}
                                        className="flex-1 py-4 bg-white text-slate-500 font-bold rounded-2xl hover:bg-slate-50 transition-colors border border-slate-200"
                                    >
                                        取消操作
                                    </button>
                                    <button
                                        onClick={() => setConfirmDelete({ show: true, userId: statsUser.id, userName: statsUser.full_name })}
                                        disabled={isDeleting}
                                        className="flex-[2] py-4 bg-red-500 text-white font-bold rounded-2xl hover:bg-red-600 hover:-translate-y-0.5 transition-all shadow-xl shadow-red-100 flex items-center justify-center gap-2 disabled:opacity-50"
                                    >
                                        {isDeleting ? (
                                            <>
                                                <FiRefreshCw className="animate-spin" />
                                                執行刪除中...
                                            </>
                                        ) : (
                                            <>
                                                <FiTrash2 />
                                                確認永久刪除
                                            </>
                                        )}
                                    </button>
                                </div>
                            </div>
                        )}
                    </Modal>

                    {/* Generation Detail Modal */}
                    <Modal
                        isOpen={isDetailModalOpen}
                        onClose={() => setIsDetailModalOpen(false)}
                        title=""
                        hideHeader={true}
                        maxWidth="max-w-6xl"
                    >
                        {selectedGeneration && (
                            <div className="space-y-6 py-4 px-6">
                                {(() => {
                                    const allGens = experimentStats?.rq_metrics?.rq1?.edit_efficiency || [];
                                    const history = allGens.filter((g: any) =>
                                        (g.course_content_id === selectedGeneration.course_content_id && g.course_content_id != null) ||
                                        (g.session_id === selectedGeneration.session_id && g.session_id != null) ||
                                        (g.job_id === selectedGeneration.job_id)
                                    ).sort((a: any, b: any) => (a.regen_index || 0) - (b.regen_index || 0));
                                    (window as any)._currentHistory = history;
                                    return null;
                                })()}
                                {/* Header Info */}
                                <div className="flex items-center justify-between pb-6">
                                    <div>
                                        <h3 className="text-3xl font-black text-slate-800 mb-2 leading-tight">{selectedGeneration?.title || '未命名內容'}</h3>
                                        <div className="flex items-center gap-4 text-base text-slate-400 font-bold">
                                            <span className="flex items-center gap-1.5"><FiCalendar /> {selectedGeneration?.created_at ? formatDateTime(selectedGeneration.created_at) : 'N/A'}</span>
                                            <span className="w-1 h-1 bg-slate-200 rounded-full" />
                                            <span className="text-slate-500 uppercase tracking-wider">{selectedGeneration.content_tag}</span>
                                            <span className="w-1 h-1 bg-slate-200 rounded-full" />
                                            {selectedGeneration.is_saved ? (
                                                <div className="flex items-center gap-2">
                                                    <span className="px-3 py-1 bg-emerald-50 text-emerald-600 rounded text-xs font-black border border-emerald-100">
                                                        已採用
                                                    </span>
                                                    {selectedGeneration.course_content_id && (
                                                        <span className="px-3 py-1 bg-slate-100 rounded text-xs font-black text-slate-500 border border-slate-200">
                                                            ID: C-{selectedGeneration.course_content_id}
                                                        </span>
                                                    )}
                                                </div>
                                            ) : (
                                                <span className="px-3 py-1 bg-slate-100 rounded text-xs font-black text-slate-400 border border-slate-200">
                                                    未採用
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Top Summary: Input Config */}
                                <div className="bg-gradient-to-br from-indigo-900 via-blue-900 to-indigo-950 rounded-[32px] p-8 text-slate-300 relative overflow-hidden group shadow-xl border border-white/5 mb-4">
                                    <div className="absolute -top-12 -right-12 p-8 opacity-[0.05] pointer-events-none rotate-12 transition-all duration-1000 group-hover:opacity-[0.08] group-hover:rotate-0">
                                        <FiZap size={240} />
                                    </div>
                                    <div className="flex items-center justify-between mb-10 relative z-10 px-4">
                                        <div className="flex items-center gap-4">
                                            <h6 className="text-xl font-black text-white uppercase tracking-wider">生成設定概覽 (INPUT CONFIG)</h6>
                                            <button 
                                                onClick={() => handleSaveSeed(selectedGeneration.job_id)}
                                                className="px-3 py-1 bg-indigo-500/20 hover:bg-indigo-500/40 text-indigo-200 text-xs font-bold rounded-lg transition-all border border-indigo-500/30 flex items-center gap-1.5 backdrop-blur-sm"
                                                title="將此設定儲存為消融實驗種子"
                                            >
                                                <AiTwotoneExperiment size={14} /> 設為實驗種子
                                            </button>
                                        </div>
                                        <div className="flex items-center gap-4 text-[11px] font-bold text-indigo-100 bg-white/10 px-5 py-2.5 rounded-2xl border border-white/10 backdrop-blur-sm">
                                            <span>重新生成: {Math.max(0, ((window as any)._currentHistory?.length || 1) - 1)} 次</span>

                                            <div className="w-[1px] h-4 bg-white/20" />
                                            <span className="opacity-80">SESSION ID: {selectedGeneration.session_id?.slice(0, 8) || 'N/A'}</span>
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 relative z-10 px-6">
                                        <div className="space-y-4">
                                            <p className="text-xs font-black text-indigo-300 uppercase tracking-[0.2em] flex items-center gap-2 opacity-70">
                                                <FiTarget size={14} /> 最終採用提示詞
                                            </p>
                                            <div className="pl-6 border-l-2 border-indigo-500/30">
                                                {(() => {
                                                    const prompt = selectedGeneration.prep_stats?.final_prompt || selectedGeneration.input_config?.prompt;
                                                    if (!prompt || prompt === '使用系統預設流程生成') {
                                                        return <p className="text-lg text-white/30 italic font-medium">無</p>;
                                                    }
                                                    return (
                                                        <p className="text-base leading-relaxed text-white italic font-medium">
                                                            「{prompt}」
                                                        </p>
                                                    );
                                                })()}
                                            </div>
                                        </div>
                                        <div className="space-y-4">
                                            <p className="text-xs font-black text-amber-600 uppercase tracking-[0.2em] flex items-center gap-2 opacity-70">
                                                <HiOutlineLightBulb size={16} /> 指定核心知識點
                                            </p>
                                            <div className="pl-6 border-l-2 border-amber-500/30">
                                                <div className="flex flex-wrap gap-2">
                                                    {(() => {
                                                        const autoKps = new Set(selectedGeneration.input_config?.job_context?.knowledge_points || []);
                                                        const kps = Array.from(new Set([
                                                            ...(selectedGeneration.input_config?.job_context?.selected_kp_names || []),
                                                            ...(selectedGeneration.prep_stats?.selected_kp_names || [])
                                                        ])).filter(Boolean);

                                                        if (kps.length === 0) return <span className="text-sm text-slate-400 italic">自動提取中</span>;

                                                        return kps.map((k: string, i: number) => {
                                                            const dbSourceType = experimentStats?.kp_source_types?.[k];
                                                            const isAuto = dbSourceType ? dbSourceType === 'extracted' : autoKps.has(k);
                                                            const label = dbSourceType ? (dbSourceType === 'extracted' ? '提取' : '手動') : (isAuto ? '提取' : '手動');

                                                            return (
                                                                <span key={i} className="px-4 py-2 bg-white/10 rounded-xl text-sm font-bold text-white border border-white/5 backdrop-blur-sm transition-all hover:bg-white/20 flex items-center gap-2">
                                                                    {k}
                                                                    <span className="w-px h-3 bg-white/20" />
                                                                    <span className="text-[10px] uppercase tracking-tighter text-amber-600">
                                                                        {label}
                                                                    </span>
                                                                </span>
                                                            );
                                                        });
                                                    })()}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {(() => {
                                    const history = (window as any)._currentHistory || [selectedGeneration];
                                    return history.map((gen: any, idx: number) => (
                                        <div key={idx} className="space-y-4 py-4 first:pt-0">
                                            <div className="flex items-center gap-6 pb-3">
                                                <div className="flex items-center gap-4 flex-none">
                                                    <div className="px-5 py-2 bg-gradient-to-r from-blue-600 to-indigo-700 text-white rounded-full text-[11px] font-black tracking-widest uppercase shadow-lg shadow-blue-100/50">
                                                        Generated Round {gen.regen_index || idx + 1}
                                                    </div>
                                                </div>

                                                <div className="flex-grow h-px bg-slate-100" />

                                                <div className="flex items-center gap-8 flex-none">
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest bg-slate-50 px-2 py-1 rounded border border-slate-100">ID:G-{gen.generated_content_id || gen.job_id || gen.id || 'N/A'}</span>
                                                    </div>
                                                    <div className="flex items-center gap-3">
                                                        <div className="w-1.5 h-1.5 rounded-full bg-slate-200" />
                                                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.1em]">{gen.created_at ? formatDateTime(gen.created_at) : ''}</span>
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="space-y-8">
                                                <div className="flex items-center justify-between">
                                                    <h6 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] flex items-center gap-2">
                                                        <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full" /> 生成前設定行為分析 (Pre-Setting Analysis)
                                                    </h6>
                                                    <div className="text-[10px] font-black text-indigo-500 bg-indigo-50 px-3 py-1 rounded-full border border-indigo-100 uppercase tracking-widest">
                                                        設定時長 T_setting: {((gen.prep_stats?.prep_duration || 0) / 60).toFixed(1)} mins
                                                    </div>
                                                </div>
                                                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                                    <div className="bg-white px-8 py-3 rounded-3xl border border-slate-100 shadow-sm flex flex-col min-h-[120px] relative overflow-hidden group transition-all duration-500 hover:shadow-xl hover:shadow-indigo-100/50">
                                                        <div className="absolute -bottom-8 -left-8 text-indigo-700/5 group-hover:text-indigo-700/10 transition-all duration-700 rotate-12 pointer-events-none">
                                                            <FiTarget size={120} />
                                                        </div>
                                                        <div className="flex items-center gap-3 mb-2 relative z-10">
                                                            <h5 className="text-base font-black text-indigo-600 uppercase tracking-wider">PROMPT 編修數據</h5>
                                                        </div>
                                                        <div className="space-y-3 flex-1">
                                                            <div className="flex justify-between items-baseline">
                                                                <span className="text-sm font-bold text-slate-500">提示詞編修次數</span>
                                                                <span className="text-2xl font-black text-indigo-600">{gen.prep_stats?.prompt_edit_count ?? 0} <span className="text-xs">次</span></span>
                                                            </div>
                                                            <div className="flex justify-between items-baseline">
                                                                <span className="text-sm font-bold text-slate-500">提示詞編修耗時</span>
                                                                <span className="text-2xl font-black text-indigo-600">{gen.prep_stats?.prompt_edit_duration?.toFixed(0) || 0} <span className="text-xs">s</span></span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <div className="bg-white px-8 py-3 rounded-3xl border border-slate-100 shadow-sm flex flex-col min-h-[120px] relative overflow-hidden group transition-all duration-500 hover:shadow-xl hover:shadow-blue-100/50">
                                                        <div className="absolute -bottom-8 -left-8 text-blue-700/5 group-hover:text-blue-700/10 transition-all duration-700 rotate-12 pointer-events-none">
                                                            <FiFileText size={120} />
                                                        </div>
                                                        <div className="flex items-center gap-3 mb-2 relative z-10">
                                                            <h5 className="text-base font-black text-blue-600 uppercase tracking-wider">
                                                                參考資料 | 共選 {gen.prep_stats?.selected_source_count || gen.input_config?.job_context?.source_ids?.length || 0} 份
                                                            </h5>
                                                        </div>
                                                        <div className="space-y-3 flex-1">
                                                            <div className="flex justify-between items-baseline">
                                                                <span className="text-sm font-bold text-slate-500">預覽切換次數</span>
                                                                <span className="text-2xl font-black text-blue-600">{gen.prep_stats?.source_preview_count || 0} <span className="text-xs">次</span></span>
                                                            </div>
                                                            <div className="flex justify-between items-baseline">
                                                                <span className="text-sm font-bold text-slate-500">選取資料總數</span>
                                                                <span className="text-2xl font-black text-blue-600">{gen.prep_stats?.selected_source_count || gen.input_config?.job_context?.source_ids?.length || 0} <span className="text-xs">個</span></span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <div className="bg-white px-8 py-3 rounded-3xl border border-slate-100 shadow-sm flex flex-col min-h-[120px] relative overflow-hidden group transition-all duration-500 hover:shadow-xl hover:shadow-amber-100/50">
                                                        <div className="absolute -bottom-8 -left-8 text-amber-700/5 group-hover:text-amber-700/10 transition-all duration-700 rotate-12 pointer-events-none">
                                                            <HiOutlineLightBulb size={120} />
                                                        </div>
                                                        <div className="flex items-center justify-between mb-2 relative z-10">
                                                            <div className="flex items-center gap-3">
                                                                <h5 className="text-base font-black text-amber-600 uppercase tracking-wider">
                                                                    KP 知識點 | 共選 {(() => {
                                                                        const kps = Array.from(new Set([
                                                                            ...(gen.input_config?.job_context?.knowledge_points || []),
                                                                            ...(gen.input_config?.job_context?.selected_kp_names || []),
                                                                            ...(gen.prep_stats?.selected_kp_names || [])
                                                                        ])).filter(Boolean);
                                                                        return kps.length;
                                                                    })()} 個
                                                                </h5>
                                                            </div>
                                                            <div className="flex flex-col items-end gap-1.5">
                                                                {(gen.prep_stats?.map_view_duration || 0) > 0 && (
                                                                    <span className="px-2 py-0.5 bg-amber-100 text-amber-600 text-[9px] font-black rounded uppercase tracking-tighter border border-amber-200">MAP_USED</span>
                                                                )}
                                                                {(gen.input_config?.job_context?.knowledge_points?.length || 0) > 0 && (
                                                                    <span className="px-2 py-0.5 bg-emerald-100 text-emerald-600 text-[9px] font-black rounded uppercase tracking-tighter border border-emerald-200">AUTO_EXTRACTED</span>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <div className="space-y-4 flex-1">
                                                            <div className="flex justify-between items-baseline">
                                                                <span className="text-sm font-bold text-slate-500">KP 編修次數</span>
                                                                <span className="text-2xl font-black text-amber-600">
                                                                    {gen.prep_stats?.kp_interaction_count || 0} <span className="text-xs">次</span>
                                                                </span>
                                                            </div>
                                                            <div className="flex justify-between items-baseline">
                                                                <span className="text-sm font-bold text-slate-500">知識地圖閱讀耗時</span>
                                                                <span className="text-2xl font-black text-amber-600">
                                                                    {gen.prep_stats?.map_view_duration?.toFixed(0) || 0} <span className="text-xs">s</span>
                                                                </span>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="py-2 space-y-4">
                                                <div className="flex items-center justify-between pt-4 border-t border-slate-50">
                                                    <h6 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] flex items-center gap-2">
                                                        <div className="w-1.5 h-1.5 bg-blue-400 rounded-full" /> 檢索品質分析 (RETRIEVAL ANALYSIS)
                                                    </h6>
                                                    <div className={`text-[10px] font-black px-3 py-1 rounded-full border uppercase tracking-widest ${gen.rag_metrics?.quality_assessment === '優秀' ? 'bg-emerald-50 text-emerald-600 border-emerald-100' :
                                                        gen.rag_metrics?.quality_assessment === '良好' ? 'bg-blue-50 text-blue-600 border-blue-100' :
                                                            'bg-amber-50 text-amber-600 border-amber-100'
                                                        }`}>
                                                        檢索品質: {gen.rag_metrics?.quality_assessment || 'N/A'}
                                                    </div>
                                                </div>

                                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
                                                    <div className="bg-white px-4 py-2.5 rounded-xl border border-slate-100 shadow-sm flex items-center justify-between">
                                                        <p className="text-[12px] font-black text-slate-500 uppercase tracking-widest whitespace-nowrap">關鍵字覆蓋率</p>
                                                        <h4 className={`text-base font-black ${(gen.rag_metrics?.keyword_coverage ?? 0) >= 0.7 ? 'text-emerald-600' : 'text-amber-500'}`}>
                                                            {((gen.rag_metrics?.keyword_coverage ?? 0) * 100).toFixed(0)}%
                                                        </h4>
                                                    </div>
                                                    <div className="bg-white px-4 py-2.5 rounded-xl border border-slate-100 shadow-sm flex items-center justify-between">
                                                        <p className="text-[12px] font-black text-slate-500 uppercase tracking-widest whitespace-nowrap">Top-1 相似度</p>
                                                        <h4 className="text-base font-black text-blue-600">
                                                            {gen.rag_metrics?.top1_vector_score?.toFixed(3) || '0.000'}
                                                        </h4>
                                                    </div>
                                                    <div className="bg-white px-4 py-2.5 rounded-xl border border-slate-100 shadow-sm flex items-center justify-between">
                                                        <p className="text-[12px] font-black text-slate-500 uppercase tracking-widest whitespace-nowrap">平均相似度</p>
                                                        <h4 className="text-base font-black text-blue-600">
                                                            {gen.rag_metrics?.avg_vector_score?.toFixed(3) || '0.000'}
                                                        </h4>
                                                    </div>
                                                    <div className="bg-white px-4 py-2.5 rounded-xl border border-slate-100 shadow-sm flex items-center justify-between">
                                                        <p className="text-[12px] font-black text-slate-500 uppercase tracking-widest whitespace-nowrap">BM25 命中數</p>
                                                        <h4 className="text-base font-black text-blue-600">
                                                            {gen.rag_metrics?.bm25_hit_count || 0}
                                                        </h4>
                                                    </div>
                                                    <div className="bg-white px-4 py-2.5 rounded-xl border border-slate-100 shadow-sm flex items-center justify-between">
                                                        <p className="text-[12px] font-black text-slate-500 uppercase tracking-widest whitespace-nowrap">內容多樣性</p>
                                                        <h4 className="text-base font-black text-blue-600">
                                                            {gen.rag_metrics?.diversity_pages || 0} 頁 / {gen.rag_metrics?.diversity_chunks || 0} 段
                                                        </h4>
                                                    </div>
                                                </div>

                                                {gen.rag_metrics?.keyword_hits && Object.keys(gen.rag_metrics.keyword_hits).length > 0 && (
                                                    <div className="flex items-start gap-4 pt-1">
                                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1.5 flex-none">知識點命中細節 (KEYWORD HITS)</p>
                                                        <div className="flex flex-wrap gap-1.5">
                                                            {Object.entries(gen.rag_metrics.keyword_hits).map(([kp, hit], kIdx) => (
                                                                <div
                                                                    key={kIdx}
                                                                    className={`px-2 py-1 rounded-md text-[9px] font-bold border transition-all flex items-center gap-1.5 ${(hit as number) > 0
                                                                        ? 'bg-emerald-50 text-emerald-700 border-emerald-100 shadow-sm shadow-emerald-100/10'
                                                                        : 'bg-white text-slate-600 border-slate-100'
                                                                        }`}
                                                                >
                                                                    {(hit as number) > 0 ? <FiCheck size={10} /> : <FiX size={10} />}
                                                                    <span className="truncate max-w-[150px]">{kp}</span>
                                                                    <span className="opacity-60">{hit as number}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>

                                            <div className="py-2 space-y-4">
                                                <div className="flex items-center justify-between pt-4 border-t border-slate-50">
                                                    <h6 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] flex items-center gap-2">
                                                        <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full" /> 生成後校驗行為分析 (POST-EDIT ANALYSIS)
                                                    </h6>
                                                    <div className="text-[10px] font-black text-slate-500 bg-slate-50 px-3 py-1 rounded-full border border-slate-100 uppercase tracking-widest">
                                                        編修時長 T_edit: {((gen.edit_duration_seconds || 0) / 60).toFixed(1)} mins
                                                    </div>
                                                </div>

                                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                                                    {/* CARD 1: EDIT DATA */}
                                                    <div className="bg-white px-5 py-2.5 rounded-2xl border border-slate-100 shadow-sm group hover:border-orange-200 transition-all flex items-center justify-between">
                                                        <div>
                                                            <p className="text-[12px] font-black text-slate-500 uppercase tracking-widest mb-0">編修幅度</p>
                                                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Edit Ratio</p>
                                                        </div>
                                                        <h4 className={`text-3xl font-black ${(gen.edit_ratio ?? 0) > 0.5 ? 'text-orange-500' : 'text-slate-800'}`}>{((gen.edit_ratio ?? 0) * 100).toFixed(0)}%</h4>
                                                    </div>

                                                    {/* CARD 2: CITATION FEEDBACK */}
                                                    <div className="bg-white px-5 py-2.5 rounded-2xl border border-slate-100 shadow-sm group hover:border-blue-200 transition-all flex items-center justify-between">
                                                        <div>
                                                            <p className="text-[12px] font-black text-slate-500 uppercase tracking-widest mb-0">參考來源</p>
                                                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Citation Clicks</p>
                                                        </div>
                                                        <h4 className="text-3xl font-black text-blue-600">{gen.citation_click_count || 0}</h4>
                                                    </div>

                                                    {/* CARD 3: AI QUALITY (CRITIC) */}
                                                    <div className="bg-white px-5 py-2.5 rounded-2xl border border-slate-100 shadow-sm group hover:border-emerald-200 transition-all flex items-center justify-between">
                                                        <div>
                                                            <p className="text-[12px] font-black text-slate-500 uppercase tracking-widest mb-0">AI 品質評估</p>
                                                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">AI Critic</p>
                                                        </div>
                                                        <h4 className={`text-3xl font-black ${(gen.critic_scores?.quality ?? 0) >= 3.5 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                                            {gen.critic_scores?.quality != null ? gen.critic_scores.quality.toFixed(1) : '0.0'}
                                                        </h4>
                                                    </div>

                                                    {/* CARD 4: TEACHER RATING */}
                                                    {(() => {
                                                        const dims = gen.teacher_rating_data?.dimensions;
                                                        const scores = dims ? Object.values(dims).filter((v): v is number => typeof v === 'number' && v > 0) : [];
                                                        const avg = scores.length > 0
                                                            ? scores.reduce((a, b) => a + b, 0) / scores.length
                                                            : (gen.teacher_rating || 0);

                                                        return (
                                                            <div className="bg-white px-5 py-2.5 rounded-2xl border border-slate-100 shadow-sm transition-all flex items-center justify-between">
                                                                <div>
                                                                    <p className="text-[12px] font-black text-slate-500 uppercase tracking-widest mb-0">教師評分</p>
                                                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Teacher Rating</p>
                                                                </div>
                                                                <div className="flex items-center gap-2">
                                                                    {scores.length > 0 && <FiStar className="text-amber-600 animate-pulse transition-all duration-700" size={16} />}
                                                                    <h4 className={`text-3xl font-black ${avg >= 3.5 ? 'text-emerald-500' : (avg > 0 ? 'text-rose-500' : 'text-slate-200')}`}>
                                                                        {avg > 0 ? avg.toFixed(1) : '--'}
                                                                    </h4>
                                                                </div>
                                                            </div>
                                                        );
                                                    })()}
                                                </div>

                                                {/* FULL WIDTH COMMENT SECTION */}
                                                {gen.teacher_rating_data?.feedback && gen.teacher_rating_data.feedback !== "無文字回饋" && (
                                                    <div className="pt-4">
                                                        <div className="flex items-center gap-3 mb-2">
                                                            <h6 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">教師回饋</h6>
                                                        </div>
                                                        <p className="text-base text-blue-600 leading-relaxed italic font-bold">
                                                            "{gen.teacher_rating_data.feedback}"
                                                        </p>
                                                    </div>
                                                )}
                                            </div>

                                            <div className="bg-gradient-to-br from-indigo-900 via-blue-900 to-indigo-950 rounded-3xl px-8 py-5 text-white relative overflow-hidden group shadow-2xl border border-white/10">
                                                <div className="absolute top-0 right-0 p-8 opacity-[0.05] group-hover:opacity-[0.1] transition-all duration-700 pointer-events-none -rotate-12 translate-x-4">
                                                    <FiCpu size={120} />
                                                </div>
                                                <div className="flex flex-wrap items-center justify-between gap-8 relative z-10">
                                                    <div className="flex items-center gap-6">
                                                        <div>
                                                            <p className="text-[10px] text-indigo-300 font-black uppercase mb-1.5 tracking-[0.2em] opacity-60">AI GENERATION MODEL</p>
                                                            <p className="text-2xl font-black text-white truncate max-w-[280px]">
                                                                {(() => {
                                                                    const usedModels = gen.job_stats?.used_models;
                                                                    if (Array.isArray(usedModels) && usedModels.length > 0) return usedModels.join(', ');
                                                                    if (typeof usedModels === 'string' && usedModels) return usedModels;
                                                                    return gen.input_config?.modelName || 'gpt-4o-mini';
                                                                })()}
                                                            </p>
                                                        </div>
                                                    </div>
                                                    <div className="flex gap-20">
                                                        <div className="text-center">
                                                            <p className="text-xs text-indigo-300/60 font-black mb-2 uppercase tracking-wide">GENERATION COST</p>
                                                            <p className="text-2xl font-black text-white flex flex-col items-center leading-tight">
                                                                <span>NT${((gen.job_stats?.total_cost_usd || 0.0001) * 32).toFixed(2)}</span>
                                                                <span className="text-xs text-amber-600 font-bold mt-1.5">${gen.job_stats?.total_cost_usd?.toFixed(4) || '0.0001'} USD</span>
                                                            </p>
                                                        </div>
                                                        <div className="text-center">
                                                            <p className="text-xs text-indigo-300/60 font-black mb-2 uppercase tracking-wide">TOTAL TOKENS</p>
                                                            <p className="text-2xl font-black text-white">{gen.job_stats?.total_tokens?.toLocaleString() || '4k'}</p>
                                                        </div>
                                                        <div className="text-center">
                                                            <p className="text-xs text-indigo-300/60 font-black mb-2 uppercase tracking-wide">CARBON FOOTPRINT</p>
                                                            <p className="text-2xl font-black text-emerald-400 uppercase">
                                                                {(() => {
                                                                    const impact = gen.job_stats?.environmental_impact;
                                                                    if (typeof impact === 'string' && impact) return impact;
                                                                    if (typeof impact === 'object' && impact && 'carbon_g' in impact) return `${(impact as any).carbon_g?.toFixed(2)}g`;
                                                                    return 'Neutral';
                                                                })()}
                                                            </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ));
                                })()}
                            </div>
                        )}
                    </Modal>

                    {
                        confirmDelete.show && (
                            <ConfirmDialog
                                isOpen={confirmDelete.show}
                                title="永久刪除使用者"
                                message={`確定要永久刪除使用者 ${confirmDelete.userName} 嗎？此操作將會刪除該使用者及其所有關聯資料（課程、作業、紀錄等），且完全不可復原。`}
                                onConfirm={() => confirmDelete.userId && handleDeleteUser(confirmDelete.userId)}
                                onCancel={() => setConfirmDelete({ show: false, userId: null, userName: '' })}
                                confirmText="確認永久刪除"
                                cancelText="取消"
                                variant="danger"
                            />
                        )
                    }

                    {
                        toast && (
                            <Toast
                                message={toast.message}
                                type={toast.type}
                                onClose={() => setToast(null)}
                            />
                        )
                    }
                </div>
            </main>
            <Footer />

            {/* SRL Scatter Tooltip Overlay */}
            {srlTooltip && srlTooltip.students && (
                <div
                    ref={srlTooltipRef}
                    className={`fixed z-[9999] transform -translate-x-1/2 -translate-y-[calc(100%+12px)] transition-all duration-200 ${srlTooltip.isLocked ? 'pointer-events-auto' : 'pointer-events-none'}`}
                    style={{ left: srlTooltip.x, top: srlTooltip.y }}
                >
                    <div className={`
                        bg-slate-900/95 backdrop-blur-md text-white p-4 rounded-2xl shadow-2xl border flex flex-col gap-2 min-w-[220px]
                        ${srlTooltip.isLocked ? 'border-blue-400/50 shadow-blue-500/20' : 'border-white/10 shadow-black/40'}
                    `}>
                        <div className="flex items-center justify-between border-b border-white/20 pb-2 mb-1">
                            <div className="flex items-center min-w-0 flex-1">
                                <div className="flex flex-col min-w-0 flex-1">
                                    <div className="flex flex-col max-h-[200px] overflow-hidden gap-1.5">
                                        {(srlTooltip.students || []).slice(0, 5).map((s: any, idx: number) => (
                                            <div key={idx} className="flex items-center justify-between gap-4">
                                                <span className="text-sm font-black truncate text-blue-300">
                                                    {s.student_name || 'Anonymous Student'}
                                                </span>
                                                <div className="flex items-center gap-2 shrink-0">
                                                    <div className="w-16 h-1 bg-white/10 rounded-full overflow-hidden">
                                                        <div
                                                            className="h-full bg-blue-300 rounded-full transition-all duration-500"
                                                            style={{ width: `${Math.min(s.lei_score || 0, 100)}%` }}
                                                        />
                                                    </div>
                                                    <span className="text-[10px] font-bold text-blue-300/80 w-8 text-right">{(s.lei_score || 0).toFixed(0)}%</span>
                                                </div>
                                            </div>
                                        ))}
                                        {(srlTooltip.students?.length || 0) > 5 && (
                                            <span className="text-[9px] opacity-50 mt-1 italic">... and {srlTooltip.students.length - 5} others</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div className="space-y-2 py-1">
                            <div className="flex justify-between items-center text-[11px] font-bold">
                                <span className="opacity-50 font-medium">{srlTooltip.dim?.xLabel || 'Metric X'}</span>
                                <span className="text-blue-200">
                                    {(() => {
                                        const val = srlTooltip.students[0]?.metrics?.[srlTooltip.dim?.xKey] || 0;
                                        if (srlTooltip.dim?.xUnit === '秒') {
                                            const mins = Math.floor(val / 60);
                                            const secs = val % 60;
                                            return mins > 0 ? `${mins} 分 ${secs} 秒` : `${secs} 秒`;
                                        }
                                        return `${val} ${srlTooltip.dim?.xUnit || ''}`;
                                    })()}
                                </span>
                            </div>
                            <div className="flex justify-between items-center text-[11px] font-bold">
                                <span className="opacity-50 font-medium">{srlTooltip.dim?.yLabel || 'Metric Y'}</span>
                                <span className="text-blue-200">
                                    {(srlTooltip.dim?.yKey === 'lei_score'
                                        ? (srlTooltip.students[0]?.lei_score || 0)
                                        : (srlTooltip.students[0]?.metrics?.[srlTooltip.dim?.yKey] || 0)
                                    ).toFixed(1)} {srlTooltip.dim?.yUnit || ''}
                                </span>
                            </div>
                        </div>
                    </div>
                    {/* Tooltip Arrow */}
                    <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-[8px] border-l-transparent border-r-[8px] border-r-transparent border-t-[8px] border-t-slate-900/95" />
                </div>
            )}
        </div>
    );
}
