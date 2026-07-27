import { useState, useMemo, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FaExclamationTriangle, FaSpinner, FaDownload, FaSearch, FaEdit, FaCheck, FaTimes, FaCheckCircle, FaExclamationCircle, FaFileDownload } from 'react-icons/fa';
import { GrScorecard } from "react-icons/gr";
import { getCourseGrades, updateGradeWeights, updateSubmissionGrade, WeightUpdateItem, UpdateSubmissionGradeItem } from '../../services/teacherGradesApi';
import { authClient } from '../../services/authClient';
import Toast from '../../components/common/Toast';
import Spinner from '../../components/common/Spinner';

interface CourseDetail {
    id: number;
    name: string;
    semester: string;
    description: string;
    teacher_name: string;
    teacher_email?: string;
    teacher_department?: string;
}

// Internal Component: Student Detail Modal
const StudentDetailModal = ({ isOpen, onClose, student }: { isOpen: boolean, onClose: () => void, student: any }) => {
    if (!isOpen || !student) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200" onClick={onClose}>
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl overflow-hidden animate-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
                <div className="relative h-24 bg-gradient-to-r from-blue-600 to-indigo-600">
                    <button onClick={onClose} className="absolute top-4 right-4 p-2 text-white/80 hover:text-white hover:bg-white/10 rounded-full transition-colors">
                        <FaTimes />
                    </button>
                </div>

                <div className="px-6 pb-8 text-center -mt-12">
                    <div className="inline-flex w-24 h-24 rounded-full border-4 border-white bg-white shadow-lg items-center justify-center text-3xl font-bold text-blue-600 mb-4 overflow-hidden bg-gradient-to-br from-blue-50 to-indigo-50">
                        {student.full_name.charAt(0)}
                    </div>

                    <h3 className="text-2xl font-bold text-gray-800 mb-1">{student.full_name}</h3>
                    <p className="text-blue-600 font-medium text-sm mb-6">{student.email}</p>

                    <div className="grid grid-cols-2 gap-4 text-left">
                        <div className="bg-gray-50 p-4 rounded-xl border border-gray-100">
                            <span className="block text-[10px] text-gray-400 font-black uppercase tracking-wider mb-1">學號</span>
                            <span className="font-bold text-gray-700">{student.student_id || '(未設定)'}</span>
                        </div>
                        <div className="bg-gray-50 p-4 rounded-xl border border-gray-100">
                            <span className="block text-[10px] text-gray-400 font-black uppercase tracking-wider mb-1">科系</span>
                            <span className="font-bold text-gray-700">{student.major || '(未設定)'}</span>
                        </div>
                    </div>

                    <div className="mt-6 pt-6 border-t border-gray-100">
                        <div className="flex items-center justify-between text-sm">
                            <span className="text-gray-500 font-medium">學期總成績</span>
                            <span className="text-2xl font-black text-blue-600">{student.total_percentage.toFixed(1)} <span className="text-xs">%</span></span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

// Internal Component: Submission Detail Modal
const SubmissionDetailModal = ({ isOpen, onClose, data, isMutationPending, onSave }: { isOpen: boolean, onClose: () => void, data: any, isMutationPending: boolean, onSave: (p: any) => void }) => {
    const [localScore, setLocalScore] = useState<number | string>(0);
    const [localGrade, setLocalGrade] = useState<any[]>([]);
    const [localGeneralFeedback, setLocalGeneralFeedback] = useState<string>('');

    useEffect(() => {
        if (data && data.details) {
            // sync score: if data.score is 0 or null, use percentage as fallback
            const initialScore = (data.score !== null && data.score !== 0) ? data.score : (data.percentage || 0);
            setLocalScore(Math.round(initialScore));

            // Handle different grade formats
            let grades: any[] = [];
            if (Array.isArray(data.details)) {
                grades = data.details;
            } else if (data.details.questions && Array.isArray(data.details.questions)) {
                grades = data.details.questions;
            } else if (data.details.details && Array.isArray(data.details.details)) {
                grades = data.details.details;
            }

            setLocalGrade([...grades]);
            // If it's a file submission or general assignment, sync the general feedback if it exists in data.details
            const feedback = data.details?.general_feedback || (typeof data.details === 'string' ? data.details : '');
            setLocalGeneralFeedback(feedback);
        } else if (data) {
            setLocalScore(Math.round(data.score ?? 0));
            setLocalGrade([]);
            setLocalGeneralFeedback('');
        }
    }, [data]);

    if (!isOpen || !data) return null;

    const { studentName, contentTitle, userId, contentId } = data;

    const handleFeedbackChange = (index: number, feedback: string) => {
        const newGrade = [...localGrade];
        newGrade[index] = { ...newGrade[index], feedback };
        setLocalGrade(newGrade);
    };

    const handleDownload = async (filename: string, originalName: string) => {
        try {
            const blob = await authClient.get<Blob>(
                `/api/teacher/file-submissions/download-file/${data.id}/${filename}`,
                undefined,
                { responseType: 'blob' }
            );
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', originalName);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Download failed:', error);
            alert('檔案下載失敗，請嘗試連繫系統管理員。');
        }
    };

    const handleSave = () => {
        onSave({
            user_id: userId,
            content_id: contentId,
            score: Number(localScore) || 0,
            grade: localGrade.length > 0 ? localGrade : { general_feedback: localGeneralFeedback }
        });
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200" onClick={onClose}>
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="p-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                    <div>
                        <h3 className="font-bold text-lg text-gray-800 flex items-center gap-2">
                            <GrScorecard className="text-blue-600" />
                            {contentTitle}
                        </h3>
                        <div className="flex items-center gap-2">
                            <p className="text-sm text-gray-500">學生：{studentName}</p>
                            {data.is_manual ? (
                                <FaCheckCircle className="text-green-500" size={14} title="教師已查核" />
                            ) : data.files && data.files.length > 0 ? (
                                <span className="text-[10px] px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded-md font-black uppercase tracking-tighter border border-blue-200">待批改</span>
                            ) : (
                                <span className="text-[10px] px-2 py-0.5 bg-amber-500 text-white rounded-md font-black uppercase tracking-tighter border border-amber-600 shadow-sm flex items-center gap-1 animate-pulse">
                                    <FaExclamationCircle size={8} /> 待查核 (AI)
                                </span>
                            )}
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        {data.score !== undefined && (
                            <div className="flex items-center gap-2">
                                <div className="flex items-center gap-2 bg-white border border-gray-200 px-3 py-1.5 rounded-lg shadow-sm">
                                    <span className="text-xs font-bold text-gray-500">得分</span>
                                    <input
                                        type="number"
                                        value={localScore}
                                        onChange={(e) => setLocalScore(e.target.value)}
                                        className="w-16 text-center font-bold text-blue-600 border-none p-0 focus:ring-0"
                                    />
                                </div>
                                <button
                                    onClick={() => setLocalScore('100')}
                                    className="px-3 py-1.5 bg-green-50 text-green-600 border border-green-200 rounded-lg text-xs font-bold hover:bg-green-100 transition-colors"
                                    title="快速評為滿分"
                                >
                                    評為滿分
                                </button>
                            </div>
                        )}
                        <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-200 rounded-full transition-colors">
                            <FaTimes />
                        </button>
                    </div>
                </div>

                {/* Body */}
                <div className="p-6 overflow-y-auto custom-scrollbar space-y-6 bg-white">
                    {localGrade.length > 0 ? (
                        localGrade.map((q: any, index: number) => (
                            <div key={index} className="border border-gray-100 rounded-lg p-4 bg-gray-50/30 hover:bg-gray-50 transition-colors">
                                {/* Question Text */}
                                <div className="font-medium text-gray-800 mb-3 flex gap-2">
                                    <span className="text-gray-400 font-bold select-none">{index + 1}.</span>
                                    <div className="markdown-content">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{q.question_text}</ReactMarkdown>
                                    </div>
                                </div>

                                {/* Answer Section */}
                                <div className="space-y-3 text-sm mb-3">
                                    <div className={`p-3 rounded-lg border w-full ${q.correctness === 'correct' ? 'bg-green-50 border-green-200 text-green-800' :
                                        q.correctness === 'partial' ? 'bg-amber-50 border-amber-200 text-amber-800' :
                                            q.correctness === 'incorrect' ? 'bg-red-50 border-red-200 text-red-800' : 'bg-gray-50 border-gray-200 text-gray-700'
                                        }`}>
                                        <div className="flex items-center gap-2 mb-1">
                                            <span className="text-[10px] uppercase font-bold tracking-wider opacity-70">學生答案</span>
                                            {q.correctness === 'correct' && <FaCheck size={10} />}
                                            {q.correctness === 'partial' && <FaExclamationCircle size={10} className="text-amber-500" />}
                                            {q.correctness === 'incorrect' && <FaTimes size={10} />}
                                        </div>
                                        <div className="font-medium markdown-content text-sm">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{q.student_answer || '(未作答)'}</ReactMarkdown>
                                        </div>
                                    </div>

                                    {q.correct_answer && (
                                        <div className="p-3 rounded-lg border w-full bg-blue-50 border-blue-200 text-blue-800">
                                            <span className="block text-[10px] uppercase font-bold tracking-wider opacity-70 mb-1">參考答案</span>
                                            <div className="font-medium markdown-content text-sm">
                                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{q.correct_answer}</ReactMarkdown>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {/* Feedback Section - Changed to Blue */}
                                <div className="mt-3 text-sm text-gray-600 bg-blue-50/50 p-3 rounded-lg border border-blue-100/50 flex flex-col gap-2 shadow-inner">
                                    <div className="flex items-center gap-2">
                                        <span className="font-bold text-blue-500 text-xs uppercase tracking-wider">評語與建議</span>
                                        <FaEdit className="text-[10px] text-blue-300" />
                                    </div>
                                    <textarea
                                        value={q.feedback || ''}
                                        onChange={(e) => handleFeedbackChange(index, e.target.value)}
                                        placeholder="輸入給學生的建議..."
                                        className="w-full bg-transparent border-none p-0 text-sm italic focus:ring-0 resize-none min-h-[64px] placeholder:text-blue-200"
                                    />
                                </div>
                            </div>
                        ))
                    ) : (
                        <div className="flex flex-col gap-6">
                            {/* File List for File Uploads */}
                            {data.files && data.files.length > 0 && (
                                <div className="space-y-3">
                                    <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
                                        <FaDownload size={10} />
                                        繳交文件 ({data.files.length})
                                    </h4>
                                    <div className="grid grid-cols-1 gap-2">
                                        {data.files.map((file: any, fidx: number) => (
                                            <button
                                                key={fidx}
                                                onClick={() => handleDownload(file.name, file.original_name)}
                                                className="flex items-center justify-between p-3 bg-blue-50/50 border border-blue-100 rounded-lg hover:bg-blue-50 transition-colors group w-full text-left"
                                            >
                                                <div className="flex items-center gap-3">
                                                    <div className="w-8 h-8 rounded bg-blue-100 flex items-center justify-center text-blue-600">
                                                        <FaFileDownload size={14} />
                                                    </div>
                                                    <div>
                                                        <div className="text-sm font-bold text-gray-800 line-clamp-1">{file.original_name}</div>
                                                        <div className="text-[10px] text-gray-500">{(file.size / 1024).toFixed(1)} KB · {new Date(file.uploaded_at).toLocaleString('zh-TW')}</div>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-1.5 text-xs font-bold text-blue-600 opacity-0 group-hover:opacity-100 transition-opacity">
                                                    <span>下載</span>
                                                    <FaDownload size={10} />
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* General Feedback Area for Assignments without questions */}
                            <div className="bg-blue-50/50 p-4 rounded-xl border border-blue-100 shadow-inner">
                                <span className="font-bold text-blue-600 text-xs uppercase tracking-wider block mb-2">評語與建議</span>
                                <textarea
                                    value={localGeneralFeedback}
                                    onChange={(e) => setLocalGeneralFeedback(e.target.value)}
                                    placeholder="輸入個人評語與建議..."
                                    className="w-full bg-transparent border-none p-0 text-sm focus:ring-0 resize-none min-h-[120px] placeholder:text-blue-300"
                                />
                            </div>

                            {(!data.files || data.files.length === 0) && (
                                <div className="flex flex-col items-center justify-center py-6 text-gray-400">
                                    <FaExclamationTriangle className="text-2xl mb-2 opacity-20" />
                                    <p className="text-sm">尚無詳細作答記錄</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-gray-100 bg-gray-50 flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-5 py-2 bg-white border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium text-sm transition-colors shadow-sm"
                    >
                        取消
                    </button>
                    {data.score !== undefined && (
                        <button
                            onClick={handleSave}
                            disabled={isMutationPending}
                            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-bold text-sm transition-all shadow-md shadow-blue-200 flex items-center gap-2"
                        >
                            {isMutationPending ? <FaSpinner className="animate-spin" /> : <FaCheck />}
                            儲存評分
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};


const GradesOverview = () => {
    const { courseId } = useParams<{ courseId: string }>();
    const queryClient = useQueryClient();
    // const { setBreadcrumbPaths } = useOutletContext<OutletContext>();

    const [searchTerm, setSearchTerm] = useState('');
    const [localWeights, setLocalWeights] = useState<Record<number, number>>({});
    const [isBulkEditing, setIsBulkEditing] = useState(false);
    const [selectedSubmission, setSelectedSubmission] = useState<{ studentName: string, contentId: number, userId: number, contentTitle: string, details: any, score: number | null, percentage?: number, id?: number, files?: any[], is_manual?: boolean } | null>(null);
    const [selectedStudent, setSelectedStudent] = useState<any | null>(null);
    const [toast, setToast] = useState<{ show: boolean, message: string, type: 'success' | 'error' | 'info' }>({ show: false, message: '', type: 'success' });
    const [showPractice, setShowPractice] = useState(true);

    // 1. Fetch Grades Data
    const { data, isLoading: isLoadingGrades, error: gradesError } = useQuery({
        queryKey: ['course-grades', courseId, showPractice],
        queryFn: () => getCourseGrades(courseId!, showPractice),
        enabled: !!courseId,
    });

    // Fetch course details for teacher info
    const { data: course, isLoading: isLoadingCourse } = useQuery<CourseDetail>({
        queryKey: ['course-detail', courseId],
        queryFn: () => authClient.get(`/api/courses/${courseId}`),
        enabled: !!courseId,
    });

    const isLoading = isLoadingGrades || isLoadingCourse;
    const error = gradesError;

    // 2. Initialize local weights when data loads
    useEffect(() => {
        if (data?.contents) {
            const weights: Record<number, number> = {};
            data.contents.forEach(c => {
                weights[c.content_id] = c.weight;
            });
            setLocalWeights(weights);
        }
    }, [data]);

    // Set Breadcrumbs - handled in Teacher.tsx to avoid loops
    /*
    useEffect(() => {
        if (courseId) {
            setBreadcrumbPaths([
                { name: '課程列表', path: '/teacher' },
                { name: '成績總覽', path: `/teacher/courses/${courseId}/grades` }
            ]);
        }
    }, [courseId, setBreadcrumbPaths]);
    */

    // 3. Mutation for updating weights
    const updateWeightsMutation = useMutation({
        mutationFn: (weights: WeightUpdateItem[]) => updateGradeWeights(courseId!, weights),
        onSuccess: () => {
            setToast({ show: true, message: '權重配置已更新', type: 'success' });
            queryClient.invalidateQueries({ queryKey: ['course-grades', courseId] });
        },
        onError: (err: any) => {
            setToast({ show: true, message: err.response?.data?.detail || '更新權重失敗', type: 'error' });
        }
    });

    // 4. Mutation for manual grading
    const updateGradeMutation = useMutation({
        mutationFn: (payload: UpdateSubmissionGradeItem) => updateSubmissionGrade(courseId!, payload),
        onSuccess: () => {
            setToast({ show: true, message: '評分成功', type: 'success' });
            queryClient.invalidateQueries({ queryKey: ['course-grades', courseId, showPractice] });
            setSelectedSubmission(null);
        },
        onError: (err: any) => {
            setToast({ show: true, message: err.response?.data?.detail || '評分失敗', type: 'error' });
        }
    });

    // Helper: Calculate total weight from local state
    const totalWeight = useMemo(() => {
        return Object.values(localWeights).reduce((sum, w) => sum + (parseFloat(String(w)) || 0), 0);
    }, [localWeights]);

    // Helper: Filter students
    const filteredStudents = useMemo(() => {
        if (!data?.students) return [];

        const lowerTerm = searchTerm.toLowerCase();
        const filtered = !searchTerm ? data.students : data.students.filter(student =>
            student.full_name.toLowerCase().includes(lowerTerm) ||
            (student.student_id && student.student_id.toLowerCase().includes(lowerTerm)) ||
            student.email.toLowerCase().includes(lowerTerm)
        );

        // Sort by total_percentage descending
        return [...filtered].sort((a, b) => (b.total_percentage || 0) - (a.total_percentage || 0));
    }, [data?.students, searchTerm]);

    // Handler: Weight Change
    const handleWeightChange = (contentId: number, value: string) => {
        const numValue = parseFloat(value);
        if (isNaN(numValue) || numValue < 0) return; // Basic validation

        setLocalWeights(prev => ({
            ...prev,
            [contentId]: numValue
        }));
    };

    // Handler: Save Bulk Weights
    const handleSaveBulkWeights = () => {
        const payload: WeightUpdateItem[] = Object.entries(localWeights).map(([id, weight]) => ({
            content_id: parseInt(id),
            weight
        }));

        updateWeightsMutation.mutate(payload, {
            onSuccess: () => {
                setIsBulkEditing(false);
            }
        });
    };

    // Handler: Cancel Bulk Edit
    const handleCancelBulkEdit = () => {
        if (data?.contents) {
            const weights: Record<number, number> = {};
            data.contents.forEach(c => {
                weights[c.content_id] = c.weight;
            });
            setLocalWeights(weights);
        }
        setIsBulkEditing(false);
    };

    // Helper: Get Subtype Label
    const getSubtypeLabel = (type: string, subtype: string | null) => {
        const map: Record<string, string> = {
            'homework': '作業',
            'quiz': '小考',
            'midterm': '期中考',
            'final': '期末考',
            'preview': '預習',
            'review': '複習'
        };
        return subtype && map[subtype] ? map[subtype] : (type === 'exam' ? '測驗' : '練習');
    };

    const handleExportCSV = () => {
        if (!data?.students || data.students.length === 0) {
            setToast({ show: true, message: '目前無成績資料可供匯出', type: 'info' });
            return;
        }

        // CSV Headers: Basic Info + Each Content Title + Total Grade
        const contentHeaders = data.contents.map(c => `${c.title} (${getSubtypeLabel(c.content_type, c.content_subtype)})`);
        const headers = ['姓名', '學號', '科系', ...contentHeaders, '學期總成績'];

        // CSV Rows
        const rows = data.students.map(student => {
            const scores = data.contents.map(content => {
                const sub = student.submissions.find(s => s.content_id === content.content_id);
                return sub && sub.score !== null ? sub.score : '未繳交';
            });
            return [
                student.full_name,
                student.student_id || '',
                student.major || '',
                ...scores,
                student.total_percentage.toFixed(1)
            ];
        });

        // Combine into CSV string
        const csvContent = [
            headers.join(','),
            ...rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
        ].join('\n');

        // Create blob and download (with BOM for Excel)
        const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        const dateStr = new Date().toISOString().split('T')[0].replace(/-/g, '');
        link.setAttribute('download', `${course?.name || '課程'}_成績單_${dateStr}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setToast({ show: true, message: '成績單匯出成功', type: 'success' });
    };

    if (isLoading) return <div className="flex justify-center items-center h-screen"><Spinner /></div>;
    if (error) return <div className="p-8 text-red-500">載入成績失敗: {(error as any).message}</div>;
    if (!data) return null;

    return (
        <div className="mx-auto px-8 lg:px-12 py-6 max-w-[1440px] transition-all duration-300">
            {/* Header Area */}
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-6">
                {/* Left: Title + Search */}
                <div className="flex flex-col md:flex-row md:items-center gap-8 flex-1 min-w-0">
                    <div className="flex items-center gap-3 shrink-0">
                        <GrScorecard className="text-blue-600 text-3xl shrink-0" />
                        <div className="min-w-0">
                            <h1 className="text-2xl font-bold text-gray-800 whitespace-nowrap">
                                成績總覽
                            </h1>
                            <p className="text-gray-400 text-xs font-bold truncate">
                                {course?.name || '...'} | {course?.teacher_name || '...'} 教師
                            </p>
                        </div>
                    </div>

                    {/* Search Field - Lengthened Further */}
                    <div className="relative flex-1 max-w-3xl w-full">
                        <FaSearch className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
                        <input
                            type="text"
                            placeholder="搜尋學生姓名、學號或信箱..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="w-full pl-11 pr-4 h-[46px] bg-white border border-gray-200 rounded-2xl focus:ring-4 focus:ring-blue-500/5 focus:border-blue-500 outline-none transition-all text-sm shadow-sm"
                        />
                    </div>
                </div>

                {/* Right: Actions */}
                <div className="flex items-center gap-3 shrink-0 flex-wrap lg:flex-nowrap justify-end">
                    <button
                        onClick={() => setShowPractice(!showPractice)}
                        className={`flex items-center justify-center gap-2 px-6 h-[46px] rounded-xl border font-black whitespace-nowrap text-sm transition-all shadow-sm ${showPractice ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'}`}
                    >
                        {showPractice ? '隱藏教材練習' : '顯示教材練習'}
                    </button>

                    <button
                        onClick={handleExportCSV}
                        className="flex items-center justify-center gap-2 bg-white text-gray-700 px-6 h-[46px] rounded-xl border border-gray-200 hover:bg-gray-50 transition-all font-bold shadow-sm whitespace-nowrap text-sm"
                    >
                        <FaDownload className="text-gray-400" />
                        匯出
                    </button>
                </div>
            </div>



            {/* 3. Grades Table */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden flex flex-col relative group/table-container">
                <div className="overflow-x-auto custom-scrollbar max-h-[calc(100vh-200px)]">
                    <table className="w-full min-w-max border-separate border-spacing-0 border-r border-gray-200">
                        <thead>
                            <tr className="bg-gray-50 border-b border-gray-200">
                                {/* Fixed Student Info Column */}
                                <th className="sticky left-0 top-0 z-40 bg-gray-50 p-4 text-center w-[220px] min-w-[220px] border-r border-b border-gray-200">
                                    <div className="flex flex-col items-center gap-0.5">
                                        <div className="font-black text-gray-700 text-[16px]">學生資訊</div>
                                        <div className="text-[11px] text-gray-400 font-bold uppercase tracking-wider">共 {filteredStudents.length} 位學生</div>
                                    </div>
                                </th>

                                {/* Content Columns */}
                                {data.contents.map(content => (
                                    <th key={content.content_id} className="sticky top-0 z-30 p-2.5 text-center w-[160px] min-w-[160px] border-r border-b border-gray-100 last:border-r-0 bg-gray-50">
                                        <div className="flex flex-col gap-1.5 items-center">
                                            {/* Title Row */}
                                            <div className="h-[32px] flex items-center justify-center w-full">
                                                <div className="font-black text-gray-800 text-[13px] text-center line-clamp-2 whitespace-normal w-full leading-tight overflow-hidden" title={content.title}>
                                                    {content.title}
                                                </div>
                                            </div>

                                            {/* Weight & Tag Row - Aligned at bottom */}
                                            <div className="flex items-center justify-center gap-1.5 w-full mt-auto pt-1.5 border-t border-gray-100/50">
                                                <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-black whitespace-nowrap uppercase tracking-tighter border ${(content.content_subtype === 'preview' || content.content_subtype === 'review')
                                                    ? 'bg-blue-50 text-blue-600 border-blue-100'
                                                    : (content.content_type === 'exam' || content.include_in_grade)
                                                        ? 'bg-purple-50 text-purple-600 border-purple-100'
                                                        : 'bg-gray-100 text-gray-600 border-gray-200'
                                                    }`}>
                                                    {getSubtypeLabel(content.content_type, content.content_subtype)}
                                                </span>
                                                <div className="flex items-center gap-1 bg-white border border-gray-100 rounded-lg px-2 py-0.5 shadow-sm">
                                                    <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest scale-90">佔比</span>
                                                    <div className="flex items-center gap-0.5">
                                                        <input
                                                            type="number"
                                                            value={localWeights[content.content_id] ?? 0}
                                                            onChange={(e) => handleWeightChange(content.content_id, e.target.value)}
                                                            className={`w-9 text-center text-[10px] font-black border rounded transition-colors p-0 h-4 ${isBulkEditing
                                                                ? 'border-blue-500 bg-white text-gray-800'
                                                                : 'border-transparent bg-transparent text-gray-600 cursor-default'
                                                                }`}
                                                            min="0"
                                                            max="100"
                                                            step="0.1"
                                                            disabled={!isBulkEditing}
                                                        />
                                                        <span className="text-[10px] font-black text-gray-400">%</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </th>
                                ))}

                                {/* Total Grade Column */}
                                <th className="sticky right-0 top-0 z-40 bg-gray-50 p-4 text-center min-w-[170px] border-l border-b border-gray-200 shadow-none">
                                    <div className="flex flex-col gap-1.5 items-center justify-center">
                                        <div className="flex items-center justify-center">
                                            <div className="font-black text-gray-700 text-[16px]">總成績</div>
                                        </div>

                                        <div className="flex items-center justify-center gap-2 w-full pt-1.5 border-t border-gray-100/50">
                                            <div className={`text-[9px] font-black whitespace-nowrap px-2 py-1 rounded-full border shadow-sm ${totalWeight > 100 ? 'bg-amber-50 text-amber-600 border-amber-100' : 'bg-purple-50 text-purple-600 border-purple-100'
                                                }`}>
                                                佔比: {totalWeight.toFixed(1)}%
                                            </div>

                                            {isBulkEditing ? (
                                                <div className="flex items-center gap-1 bg-white border border-gray-200 rounded-full px-2 py-0.5 shadow-sm animate-in fade-in zoom-in-95 duration-200">
                                                    <button
                                                        onClick={handleSaveBulkWeights}
                                                        disabled={updateWeightsMutation.isPending}
                                                        className="w-6 h-4 flex items-center justify-center text-green-600 hover:bg-green-50 rounded-full transition-colors"
                                                        title="儲存全部"
                                                    >
                                                        {updateWeightsMutation.isPending ? <FaSpinner className="animate-spin text-[10px]" /> : <FaCheck size={10} />}
                                                    </button>
                                                    <div className="w-px h-3 bg-gray-200 mx-0.5"></div>
                                                    <button
                                                        onClick={handleCancelBulkEdit}
                                                        className="w-6 h-4 flex items-center justify-center text-red-500 hover:bg-red-50 rounded-full transition-colors"
                                                        title="取消"
                                                    >
                                                        <FaTimes size={10} />
                                                    </button>
                                                </div>
                                            ) : (
                                                <button
                                                    onClick={() => setIsBulkEditing(true)}
                                                    className="flex items-center gap-1 px-2.5 py-1 bg-white border border-gray-200 rounded-full text-[10px] font-bold text-gray-500 hover:text-blue-600 hover:border-blue-200 hover:shadow-sm transition-all group"
                                                    title="編輯所有權重"
                                                >
                                                    <FaEdit size={10} className="group-hover:scale-110 transition-transform" />
                                                    <span>編輯權重</span>
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredStudents.length > 0 ? (
                                <>
                                    {filteredStudents.map((student) => (
                                        <tr key={student.user_id} className="hover:bg-blue-50/30 transition-colors border-b border-gray-100 last:border-b-0">
                                            {/* Student Info Cell */}
                                            <td
                                                className="sticky left-0 z-20 bg-white p-4 border-r border-b border-gray-200"
                                            >
                                                <div className="flex items-center justify-start gap-3 pl-2">
                                                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-bold text-xs shadow-sm flex-shrink-0">
                                                        {student.full_name.charAt(0)}
                                                    </div>
                                                    <div className="flex flex-col text-left min-w-[120px]">
                                                        <div className="font-bold text-gray-800 line-clamp-1 flex items-center gap-1">
                                                            {student.full_name}
                                                            {student.role === 'ta' && (
                                                                <span className="text-[9px] px-1 py-0.5 bg-indigo-100 text-indigo-600 border border-indigo-200 rounded font-black">助教</span>
                                                            )}
                                                        </div>
                                                        <div className="text-[10px] text-gray-500 font-medium leading-tight">
                                                            {student.major} {student.student_id}
                                                        </div>
                                                    </div>
                                                </div>
                                            </td>

                                            {/* Grade Cells */}
                                            {data.contents.map(content => {
                                                const sub = student.submissions.find(s => s.content_id === content.content_id);
                                                const isGradedType = content.content_subtype === 'homework' || content.content_subtype === 'exam';
                                                const shouldShowScore = content.include_in_grade || (content.weight > 0) || isGradedType;

                                                return (
                                                    <td key={`${student.user_id}-${content.content_id}`} className="py-2 px-3 text-center border-r border-b border-gray-100 last:border-r-0 align-middle bg-white">
                                                        {sub && (sub.submitted_at || sub.id || (sub.grade && sub.grade.practice_count > 0)) ? (
                                                            <div
                                                                className="flex flex-col items-center justify-center cursor-pointer hover:bg-gray-100 rounded-lg p-1 transition-colors group relative"
                                                                onClick={() => setSelectedSubmission({
                                                                    studentName: student.full_name,
                                                                    userId: student.user_id,
                                                                    contentId: content.content_id,
                                                                    contentTitle: content.title,
                                                                    details: sub.grade,
                                                                    score: sub.score,
                                                                    percentage: sub.percentage ?? undefined,
                                                                    id: sub.id ?? undefined,
                                                                    files: sub.files ?? undefined,
                                                                    is_manual: sub.is_manual
                                                                })}
                                                            >
                                                                {shouldShowScore ? (
                                                                    (!sub.is_manual && sub.files && sub.files.length > 0) ? (
                                                                        <div className="flex flex-col items-center gap-1.5 min-h-[32px] justify-center">
                                                                            <div className="flex items-center gap-1.5 px-3 py-1 bg-blue-50 text-blue-600 border border-blue-200 rounded-full shadow-sm hover:shadow-md hover:bg-blue-100 transition-all duration-200 group/status w-fit mx-auto">
                                                                                <FaFileDownload className="text-blue-500 shrink-0" size={12} />
                                                                                <span className="text-xs font-bold whitespace-nowrap">待批改</span>
                                                                            </div>
                                                                        </div>
                                                                    ) : (sub.score !== null || sub.percentage !== null) ? (
                                                                        <div className="flex flex-col items-center justify-center">
                                                                            <div className="flex items-center gap-1.5">
                                                                                <span className={`text-base font-black ${((sub.score !== null && sub.score !== 0 ? sub.score : sub.percentage) || 0) >= 60 ? 'text-gray-800' : 'text-red-500'}`}>
                                                                                    {Math.round(sub.score !== null && sub.score !== 0 ? sub.score : (sub.percentage || 0))}
                                                                                </span>
                                                                                {sub.is_manual && (
                                                                                    <FaCheckCircle className="text-green-500 shrink-0" size={12} />
                                                                                )}
                                                                            </div>
                                                                            <div className="mt-1.5 flex flex-col items-center">
                                                                                {!sub.is_manual && (sub.score !== null || sub.percentage !== null) && (
                                                                                    <span className="text-[10px] px-2 py-0.5 bg-amber-500 text-white rounded-md font-black uppercase tracking-tighter border border-amber-600 shadow-sm flex items-center gap-1 animate-pulse">
                                                                                        <FaExclamationCircle size={8} /> 待查核 (AI)
                                                                                    </span>
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                    ) : (
                                                                        <div className="flex flex-col items-center gap-1.5 justify-center">
                                                                            <div className="flex items-center gap-1.5 px-3 py-1 bg-amber-50 text-amber-600 border border-amber-200 rounded-full shadow-sm hover:shadow-md hover:bg-amber-100 transition-all duration-200 group/status w-fit mx-auto">
                                                                                <FaExclamationCircle className="text-amber-500 shrink-0" size={14} />
                                                                                <span className="text-xs font-bold whitespace-nowrap">待評分</span>
                                                                            </div>
                                                                        </div>
                                                                    )
                                                                ) : (
                                                                    <div className="flex items-center gap-1.5 px-3 h-[32px] bg-blue-50 text-blue-600 border border-blue-200 rounded-full shadow-sm hover:shadow-md hover:bg-blue-100 transition-all duration-200 group/status w-fit mx-auto">
                                                                        <FaCheckCircle className="text-blue-500 shrink-0" size={14} />
                                                                        <span className="text-xs font-bold whitespace-nowrap">已作答 {sub.grade?.practice_count || 0}</span>
                                                                    </div>
                                                                )}
                                                                {/* Tooltip */}
                                                                <div className="absolute -top-8 left-1/2 -translate-x-1/2 px-2 py-1 bg-gray-800 text-white text-[10px] rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-[60]">
                                                                    點擊查看詳情
                                                                    <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-800"></div>
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <span className="text-xs text-gray-300 italic">未繳交</span>
                                                        )}
                                                    </td>
                                                );
                                            })}

                                            {/* Weighted Total Cell */}
                                            <td className="sticky right-0 z-20 bg-white p-4 text-center border-l border-b border-gray-200">
                                                <div className={`text-lg font-bold ${student.total_percentage >= 60 ? 'text-blue-600' : 'text-red-500'
                                                    }`}>
                                                    {student.total_percentage.toFixed(1)}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}

                                    {/* Average Row - Sticky at the bottom */}
                                    <tr className="sticky bottom-0 z-30 font-bold shadow-[0_-2px_4px_rgba(0,0,0,0.05)]">
                                        <td className="sticky left-0 bottom-0 z-40 bg-gray-100 p-2.5 border-r border-t border-gray-200 text-gray-700">
                                            <div className="flex flex-col items-center justify-center gap-0.5">
                                                <div className="text-xs font-black">平均成績</div>
                                                <div className="text-[10px] text-gray-400 font-bold whitespace-nowrap">顯示 {filteredStudents.length} / {data.students.length} 位學生</div>
                                            </div>
                                        </td>
                                        {data.contents.map(content => {
                                            const validScores = filteredStudents
                                                .map(s => s.submissions.find(sub => sub.content_id === content.content_id)?.score)
                                                .filter(s => s !== null && s !== undefined) as number[];
                                            const avg = validScores.length > 0
                                                ? (validScores.reduce((a, b) => a + b, 0) / validScores.length).toFixed(1)
                                                : '-';

                                            return (
                                                <td key={`avg-${content.content_id}`} className="bg-gray-100 p-3 text-center border-r border-t border-gray-200 text-gray-700">
                                                    {avg}
                                                </td>
                                            );
                                        })}
                                        <td className="sticky right-0 bottom-0 z-40 bg-gray-100 p-3 text-center border-l border-t border-gray-200 text-blue-700 font-black">
                                            {(filteredStudents.reduce((acc, s) => acc + s.total_percentage, 0) / (filteredStudents.length || 1)).toFixed(1)}
                                        </td>
                                    </tr>
                                </>
                            ) : (
                                <tr>
                                    <td colSpan={data.contents.length + 2} className="p-12 text-center text-gray-500">
                                        找不到符合條件的學生資料
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

            </div>

            {
                toast.show && (
                    <Toast
                        message={toast.message}
                        type={toast.type}
                        onClose={() => setToast(prev => ({ ...prev, show: false }))}
                    />
                )
            }
            {/* 4. Submission Details Modal */}
            <SubmissionDetailModal
                isOpen={!!selectedSubmission}
                onClose={() => setSelectedSubmission(null)}
                data={selectedSubmission}
                isMutationPending={updateGradeMutation.isPending}
                onSave={updateGradeMutation.mutate}
            />

            <StudentDetailModal
                isOpen={!!selectedStudent}
                onClose={() => setSelectedStudent(null)}
                student={selectedStudent}
            />
        </div >
    );
};

export default GradesOverview;

