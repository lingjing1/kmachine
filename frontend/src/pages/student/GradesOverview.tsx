import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    FaUserTie,
    FaChalkboardTeacher,
    FaFileDownload,
    FaTimesCircle,
    FaCheckCircle,
    FaInfoCircle,
    FaTimes,
    FaRegCommentDots
} from 'react-icons/fa';
import { GrScorecard } from 'react-icons/gr';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { studentGradesApi, StudentGradeItem } from '../../services/studentGradesApi';
import { authClient } from '../../services/authClient';

interface SubmissionModalProps {
    isOpen: boolean;
    onClose: () => void;
    data: StudentGradeItem | null;
}

const SubmissionModal: React.FC<SubmissionModalProps> = ({ isOpen, onClose, data }) => {
    if (!isOpen || !data) return null;

    const handleDownload = async (filename: string, originalName: string) => {
        try {
            const blob = await authClient.get<Blob>(
                `/api/teacher/file-submissions/download-file/${data.sub_id}/${filename}`,
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
            alert('檔案下載失敗。');
        }
    };

    const hasQuestions = Array.isArray(data.grade);
    const generalFeedback = !hasQuestions && data.grade?.general_feedback;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200" onClick={onClose}>
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="p-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                    <div>
                        <h3 className="font-bold text-lg text-gray-800 flex items-center gap-2">
                            <GrScorecard className="text-blue-600" />
                            {data.title}
                        </h3>
                        <div className="flex items-center gap-2">
                            <p className="text-sm text-gray-500">提交時間：{data.submitted_at || '未記錄'}</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="bg-white border border-gray-200 px-3 py-1.5 rounded-lg shadow-sm flex items-center gap-2">
                            <span className="text-xs font-bold text-gray-500">得分</span>
                            <span className="text-lg font-bold text-blue-600">{data.score ?? '--'}</span>
                        </div>
                        <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-200 rounded-full transition-colors">
                            <FaTimes />
                        </button>
                    </div>
                </div>

                {/* Body */}
                <div className="p-6 overflow-y-auto custom-scrollbar space-y-6 bg-white">
                    {hasQuestions ? (
                        data.grade.map((q: any, index: number) => (
                            <div key={index} className="border border-gray-100 rounded-lg p-4 bg-gray-50/30">
                                <div className="font-medium text-gray-800 mb-3 flex gap-2">
                                    <span className="text-gray-400 font-bold">{index + 1}.</span>
                                    <div className="markdown-content prose prose-sm max-w-none">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{q.question_text}</ReactMarkdown>
                                    </div>
                                </div>

                                <div className="space-y-3 text-sm mb-3">
                                    <div className={`p-3 rounded-lg border w-full ${q.correctness === 'correct' ? 'bg-green-50 border-green-200 text-green-800' :
                                        q.correctness === 'partial' ? 'bg-amber-50 border-amber-200 text-amber-800' :
                                            q.correctness === 'incorrect' ? 'bg-red-50 border-red-200 text-red-800' : 'bg-gray-50 border-gray-200 text-gray-700'
                                        }`}>
                                        <span className="block text-[10px] uppercase font-bold tracking-wider opacity-70 mb-1">你的回答</span>
                                        <div className="font-medium markdown-content prose prose-sm max-w-none">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{q.student_answer || '(未作答)'}</ReactMarkdown>
                                        </div>
                                    </div>

                                    {q.correct_answer && (
                                        <div className="p-3 rounded-lg border w-full bg-blue-50 border-blue-200 text-blue-800">
                                            <span className="block text-[10px] uppercase font-bold tracking-wider opacity-70 mb-1">參考答案</span>
                                            <div className="font-medium markdown-content prose prose-sm max-w-none">
                                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{q.correct_answer}</ReactMarkdown>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {q.feedback && (
                                    <div className="mt-3 text-sm text-gray-600 bg-blue-50/50 p-3 rounded-lg border border-blue-100/50 flex flex-col gap-2">
                                        <div className="flex items-center gap-2">
                                            <span className="font-bold text-blue-500 text-xs uppercase tracking-wider">教師評語</span>
                                        </div>
                                        <div className="text-sm italic text-gray-700">{q.feedback}</div>
                                    </div>
                                )}
                            </div>
                        ))
                    ) : (
                        <div className="space-y-6">
                            {/* File List */}
                            {data.files && data.files.length > 0 && (
                                <div className="space-y-3">
                                    <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
                                        <FaFileDownload size={10} />
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
                                                    <div className="p-2 bg-blue-100 rounded-lg group-hover:bg-blue-200 transition-colors">
                                                        <FaFileDownload className="text-blue-600" />
                                                    </div>
                                                    <div>
                                                        <div className="text-sm font-medium text-gray-700 truncate max-w-[300px]">{file.original_name}</div>
                                                        <div className="text-[10px] text-gray-400 uppercase tracking-tight">{(file.size / 1024).toFixed(1)} KB</div>
                                                    </div>
                                                </div>
                                                <FaFileDownload className="text-gray-300 group-hover:text-blue-500" />
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* General Feedback */}
                            {generalFeedback && (
                                <div className="space-y-3">
                                    <h4 className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-2">
                                        <FaRegCommentDots size={12} />
                                        教師評語與建議
                                    </h4>
                                    <div className="p-5 bg-blue-50/30 border border-blue-100 rounded-xl shadow-inner text-gray-700 leading-relaxed italic">
                                        {generalFeedback}
                                    </div>
                                </div>
                            )}

                            {!data.files && !generalFeedback && (
                                <div className="text-center py-10 text-gray-400">
                                    <FaInfoCircle className="mx-auto mb-2 opacity-20" size={32} />
                                    <p>尚無詳細作答內容或評語</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-gray-100 bg-gray-50 flex justify-end">
                    <button
                        onClick={onClose}
                        className="px-6 py-2 bg-white border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 font-medium transition-colors"
                    >
                        關閉
                    </button>
                </div>
            </div>
        </div>
    );
};

const StudentGradesOverview: React.FC = () => {
    const { courseId } = useParams<{ courseId: string }>();
    const [selectedSubmission, setSelectedSubmission] = useState<StudentGradeItem | null>(null);
    const [toast, setToast] = useState<{ show: boolean; message: string }>({ show: false, message: '' });

    const copyEmail = (email: string) => {
        navigator.clipboard.writeText(email);
        setToast({ show: true, message: 'Email 已複製！' });
        setTimeout(() => setToast({ show: false, message: '' }), 2000);
    };

    const { data: gradesData, isLoading, error } = useQuery({
        queryKey: ['student-grades', courseId],
        queryFn: () => studentGradesApi.getMyGrades(Number(courseId)),
        enabled: !!courseId
    });

    if (isLoading) {
        return (
            <div className="p-8 flex items-center justify-center min-h-[400px]">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    if (error || !gradesData) {
        return (
            <div className="p-8 text-center text-red-500">
                載入成績失敗，請確認課程資訊是否存在。
            </div>
        );
    }

    const { course_name, staff, grades, weighted_total, total_scored_weight } = gradesData;

    return (
        <div className="max-w-[1440px] mx-auto px-6 lg:px-12 py-6 animate-in fade-in slide-in-from-bottom-4 duration-500 relative transition-all">
            {/* Simple Toast */}
            {toast.show && (
                <div className="fixed top-8 left-1/2 -translate-x-1/2 z-[200] px-6 py-3 bg-gray-800 text-white rounded-full shadow-2xl font-black text-sm animate-in fade-in slide-in-from-top-4 duration-300">
                    {toast.message}
                </div>
            )}
            <div className="flex flex-col lg:flex-row gap-8 items-start">

                {/* Left Sidebar: Course Summary & Progress */}
                <div className="w-full lg:w-[260px] lg:sticky lg:top-8 space-y-6 flex-shrink-0">
                    {/* Course Card */}
                    <div className="bg-white rounded-3xl shadow-sm border border-gray-100 px-6 pt-4 pb-6 space-y-6 relative overflow-hidden min-h-[calc(100vh-8rem)] flex flex-col">
                        <div className="absolute -top-10 -right-10 w-32 h-32 bg-blue-50 rounded-full opacity-40" />

                        <div className="relative z-10 flex-grow">
                            <h1 className="text-2xl font-black text-gray-900 tracking-tight leading-tight mb-4">{course_name}</h1>

                            {/* Score Card */}
                            <div className="bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-2xl p-4 shadow-lg shadow-blue-100 flex flex-col items-center mb-6">
                                <span className="text-[10px] font-bold opacity-80 uppercase tracking-widest mb-1">學期目前累計得分</span>
                                <div className="flex items-baseline gap-1">
                                    <span className="text-3xl font-black">{weighted_total}</span>
                                    <span className="text-xs opacity-70">/ 100</span>
                                </div>
                            </div>

                            {/* Progress bar */}
                            <div className="space-y-3 mb-6">
                                <div className="flex justify-between items-end">
                                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">成績累計比例</span>
                                    <span className="text-sm font-black text-blue-600">{total_scored_weight}%</span>
                                </div>
                                <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-blue-500 rounded-full transition-all duration-1000 ease-out shadow-[0_0_8px_rgba(59,130,246,0.5)]"
                                        style={{ width: `${total_scored_weight}%` }}
                                    />
                                </div>
                                <p className="text-[10px] text-gray-400 italic text-center leading-tight">※其餘 {100 - total_scored_weight}% 尚未評分或公告</p>
                            </div>

                            {/* Staff Info */}
                            <div className="space-y-4 pt-4 border-t border-gray-50">
                                <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">授課團隊</h4>
                                <div className="space-y-3">
                                    {staff.map((member, idx) => (
                                        <div
                                            key={idx}
                                            onClick={() => copyEmail(member.email)}
                                            className="flex flex-col p-3 bg-gray-50/50 rounded-xl border border-gray-100/50 hover:bg-white hover:border-blue-200 hover:shadow-md transition-all duration-300 group cursor-pointer active:scale-95"
                                        >
                                            <div className="flex items-center gap-2 mb-1">
                                                {member.role === 'teacher' ? <FaUserTie size={12} className="text-blue-500" /> : <FaChalkboardTeacher size={12} className="text-amber-500" />}
                                                <span className="text-base font-black text-gray-700">{member.full_name}</span>
                                            </div>
                                            <span className="text-xs text-gray-400 truncate group-hover:text-blue-500 transition-colors font-medium">{member.email}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Right Content: Grades Table */}
                <div className="flex-1 min-w-0 bg-white rounded-3xl shadow-sm border border-gray-100 overflow-hidden min-h-[calc(100vh-8rem)]">
                    <div className="px-8 py-6 border-b border-gray-50 flex justify-between items-center bg-gray-50/30">
                        <h2 className="font-black text-xl text-gray-800 flex items-center gap-3">
                            <div className="p-2 bg-blue-600 rounded-xl shadow-lg shadow-blue-100">
                                <GrScorecard className="text-white" />
                            </div>
                            成績明細
                        </h2>
                    </div>

                    <div className="overflow-x-auto custom-scrollbar">
                        <table className="w-full text-left">
                            <thead>
                                <tr className="bg-gray-50/20 text-gray-400 text-[11px] font-bold uppercase tracking-widest">
                                    <th className="px-8 py-5 text-center">作業名稱</th>
                                    <th className="px-6 py-5 text-center">類型</th>
                                    <th className="px-6 py-5 text-center whitespace-nowrap">成績權重</th>
                                    <th className="px-6 py-5 text-center">得分</th>
                                    <th className="px-8 py-5 text-center">作答與回饋</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-50/50">
                                {grades.map((item) => {
                                    // Type Label Mapping (Match Teacher Panel)
                                    const map: Record<string, string> = {
                                        'homework': '作業',
                                        'assignment': '作業',
                                        'quiz': '小考',
                                        'midterm': '期中考',
                                        'final': '期末考',
                                        'preview': '預習',
                                        'review': '複習',
                                        'practice': '練習'
                                    };

                                    const typeLabel = (item.content_subtype && map[item.content_subtype]) ||
                                        (item.content_type === 'exam' ? '測驗' : '練習');

                                    // Color Logic
                                    let typeColor = 'bg-gray-50 text-gray-500 border border-gray-100';
                                    if (['quiz', 'midterm', 'final', 'exam'].includes(item.content_subtype || item.content_type)) {
                                        typeColor = 'bg-purple-50 text-purple-600 border border-purple-100';
                                    } else if (['preview', 'review', 'practice'].includes(item.content_subtype || '')) {
                                        typeColor = 'bg-blue-50 text-blue-600 border border-blue-100';
                                    } else if (item.weight > 0) {
                                        typeColor = 'bg-purple-50 text-purple-600 border border-purple-100';
                                    }

                                    return (
                                        <tr key={item.content_id} className="hover:bg-blue-50/20 transition-all duration-200 group">
                                            <td className="px-8 py-6 text-left">
                                                <div className="flex flex-col items-start">
                                                    <div className="font-bold text-gray-800 group-hover:text-blue-600 transition-colors">
                                                        {item.title}
                                                    </div>
                                                    {item.start_time && (
                                                        <div className="text-[9px] text-gray-400 mt-0.5">
                                                            公佈時間：{new Date(item.start_time).toLocaleDateString()}
                                                        </div>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="px-6 py-6 text-center">
                                                <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-black uppercase tracking-tighter whitespace-nowrap ${typeColor}`}>
                                                    {typeLabel}
                                                </span>
                                            </td>
                                            <td className="px-6 py-6 text-center">
                                                <span className="text-gray-900 font-black text-sm whitespace-nowrap">{item.weight}%</span>
                                            </td>
                                            <td className="px-6 py-6 text-center">
                                                <div className="flex items-baseline justify-center gap-1.5 min-w-[100px]">
                                                    {(item.score !== null && item.is_manual) ? (
                                                        <>
                                                            <span className="text-lg font-black text-blue-600">
                                                                {item.score}
                                                            </span>
                                                            <span className="text-[10px] text-gray-400 font-medium">/ {item.total_points}</span>
                                                        </>
                                                    ) : (item.submitted_at || item.score !== null || (item.grade && item.grade.practice_count > 0)) ? (
                                                        <div className="flex items-center gap-2 text-green-600 text-xs font-black uppercase tracking-tight whitespace-nowrap">
                                                            <FaCheckCircle size={14} className="drop-shadow-sm" />
                                                            <span>已繳交</span>
                                                        </div>
                                                    ) : (
                                                        <div className="flex items-center gap-2 text-red-500 text-xs font-black uppercase tracking-tight whitespace-nowrap">
                                                            <FaTimesCircle size={14} className="drop-shadow-sm" />
                                                            <span>未繳交</span>
                                                        </div>
                                                    )}
                                                </div>
                                            </td>
                                            <td className="px-8 py-6 text-center">
                                                {(item.sub_id || (item.grade && (item.grade.practice_count > 0 || Array.isArray(item.grade)))) ? (
                                                    <button
                                                        onClick={() => setSelectedSubmission(item)}
                                                        className="px-4 py-2 bg-white border border-gray-200 text-blue-600 rounded-xl text-[11px] font-black shadow-sm hover:shadow-md hover:bg-blue-600 hover:text-white hover:border-blue-600 transition-all duration-300 active:scale-95 whitespace-nowrap"
                                                    >
                                                        查看詳情
                                                    </button>
                                                ) : (
                                                    <span className="text-xs text-gray-300 font-medium whitespace-nowrap">--</span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <SubmissionModal
                isOpen={!!selectedSubmission}
                onClose={() => setSelectedSubmission(null)}
                data={selectedSubmission}
            />
        </div>
    );
};

export default StudentGradesOverview;
