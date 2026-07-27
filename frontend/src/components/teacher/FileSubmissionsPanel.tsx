// frontend/src/components/teacher/FileSubmissionsPanel.tsx
// Teacher panel to view, download, and grade student file submissions

import { useState, useEffect, useCallback } from 'react';
import {
    FaCloudDownloadAlt, FaFileAlt, FaUser, FaStar, FaSpinner,
    FaCheckCircle, FaTimesCircle, FaFileArchive, FaDownload,
    FaPen, FaSave, FaTimes
} from 'react-icons/fa';
import API_BASE_URL from '../../config/api';
import { authClient } from '../../services/authClient';
import { formatDateTime } from '../../utils/dateUtils';

interface SubmissionFile {
    name: string;
    original_name: string;
    path: string;
    size: number;
    type: string;
    uploaded_at: string;
}

interface FileSubmission {
    id: number;
    content_id: number;
    user_id: number;
    student_name: string;
    student_id: string | null;
    files: SubmissionFile[];
    score: number | null;
    feedback: string | null;
    submitted_at: string;
    updated_at: string | null;
}

interface FileSubmissionsPanelProps {
    contentId: number;
    contentTitle: string;
    totalPoints?: number;
}

export default function FileSubmissionsPanel({
    contentId,
    contentTitle,
    totalPoints = 100
}: FileSubmissionsPanelProps) {
    const [submissions, setSubmissions] = useState<FileSubmission[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [downloadingAll, setDownloadingAll] = useState(false);

    // Grading state
    const [editingId, setEditingId] = useState<number | null>(null);
    const [editScore, setEditScore] = useState<string>('');
    const [editFeedback, setEditFeedback] = useState<string>('');
    const [saving, setSaving] = useState(false);

    const fetchSubmissions = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const data = await authClient.get<FileSubmission[]>(`/api/teacher/file-submissions/${contentId}`);
            setSubmissions(Array.isArray(data) ? data : []);
        } catch (err: any) {
            setError(err.message || '無法載入繳交記錄');
        } finally {
            setLoading(false);
        }
    }, [contentId]);

    useEffect(() => {
        fetchSubmissions();
    }, [fetchSubmissions]);

    const handleDownloadSpecific = async (submissionId: number, filename: string, originalName: string) => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/teacher/file-submissions/download-file/${submissionId}/${filename}`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            if (!response.ok) throw new Error('下載失敗');
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = originalName;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Download error:', err);
        }
    };

    const handleDownloadAll = async () => {
        setDownloadingAll(true);
        try {
            const response = await fetch(`${API_BASE_URL}/api/teacher/file-submissions/${contentId}/download-all`, {
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            if (!response.ok) throw new Error('下載失敗');
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `submissions_${contentId}.zip`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Download all error:', err);
        } finally {
            setDownloadingAll(false);
        }
    };

    const startEditing = (sub: FileSubmission) => {
        setEditingId(sub.id);
        setEditScore(sub.score !== null ? String(sub.score) : '');
        setEditFeedback(sub.feedback || '');
    };

    const cancelEditing = () => {
        setEditingId(null);
        setEditScore('');
        setEditFeedback('');
    };

    const handleSaveGrade = async (submissionId: number) => {
        setSaving(true);
        try {
            const scoreNum = editScore ? parseFloat(editScore) : null;
            await authClient.put(`/api/teacher/file-submissions/${submissionId}/grade`, {
                score: scoreNum,
                feedback: editFeedback || null
            });
            // Update local state
            setSubmissions(prev => prev.map(s =>
                s.id === submissionId
                    ? { ...s, score: scoreNum, feedback: editFeedback || null }
                    : s
            ));
            cancelEditing();
        } catch (err: any) {
            console.error('Grade save error:', err);
        } finally {
            setSaving(false);
        }
    };

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const formatDate = (dateStr: string) => {
        return formatDateTime(dateStr);
    };

    const gradedCount = submissions.filter(s => s.score !== null).length;

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12 text-gray-400 gap-2">
                <FaSpinner className="animate-spin" />
                <span>載入繳交記錄中...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center py-12 text-red-500 gap-2">
                <FaTimesCircle />
                <span>{error}</span>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                        <FaFileAlt className="text-blue-500" />
                        繳交記錄
                        <span className="text-sm font-normal text-gray-500">
                            — {contentTitle}
                        </span>
                    </h3>
                    <p className="text-sm text-gray-500 mt-1">
                        共 {submissions.length} 人繳交・已評分 {gradedCount}/{submissions.length}
                    </p>
                </div>
                {submissions.length > 0 && (
                    <button
                        onClick={handleDownloadAll}
                        disabled={downloadingAll}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-all shadow-sm"
                    >
                        {downloadingAll ? (
                            <FaSpinner className="animate-spin" />
                        ) : (
                            <FaFileArchive />
                        )}
                        下載全部 (ZIP)
                    </button>
                )}
            </div>

            {/* Empty state */}
            {submissions.length === 0 ? (
                <div className="text-center py-12 text-gray-400 border border-dashed border-gray-200 rounded-xl bg-gray-50">
                    <FaCloudDownloadAlt className="mx-auto text-3xl mb-2" />
                    <p className="font-medium">尚無學生繳交</p>
                </div>
            ) : (
                /* Submissions list */
                <div className="border border-gray-200 rounded-xl overflow-hidden">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="bg-gray-50 border-b border-gray-200">
                                <th className="text-center px-4 py-3 font-semibold text-gray-600">學生</th>
                                <th className="text-center px-4 py-3 font-semibold text-gray-600 min-w-[200px]">繳交檔案</th>
                                <th className="text-center px-4 py-3 font-semibold text-gray-600">繳交時間</th>
                                <th className="text-center px-4 py-3 font-semibold text-gray-600">分數</th>
                                <th className="text-center px-4 py-3 font-semibold text-gray-600">操作</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                            {submissions.map((sub) => (
                                <tr key={sub.id} className="hover:bg-gray-50 transition-colors">
                                    {/* Student */}
                                    <td className="px-4 py-3">
                                        <div className="flex items-center gap-2">
                                            <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-xs">
                                                {sub.student_name?.charAt(0) || <FaUser />}
                                            </div>
                                            <div>
                                                <div className="font-medium text-gray-800">{sub.student_name}</div>
                                                <div className="text-xs text-gray-400">{sub.student_id || ''}</div>
                                            </div>
                                        </div>
                                    </td>

                                    {/* Files */}
                                    <td className="px-4 py-3">
                                        <div className="flex flex-col gap-1.5">
                                            {sub.files && sub.files.length > 0 ? (
                                                sub.files.map((file) => (
                                                    <div key={file.name} className="flex items-center justify-between gap-4 group/file">
                                                        <div className="flex items-center gap-2 overflow-hidden">
                                                            <FaFileAlt className="text-blue-400 shrink-0" size={14} />
                                                            <span className="text-xs text-gray-700 truncate max-w-[300px]" title={file.original_name}>
                                                                {file.original_name}
                                                            </span>
                                                            <span className="text-[10px] text-gray-400 shrink-0">({formatFileSize(file.size)})</span>
                                                        </div>
                                                        <button
                                                            onClick={() => handleDownloadSpecific(sub.id, file.name, file.original_name)}
                                                            className="text-blue-500 hover:text-blue-700 transition-all flex-shrink-0"
                                                            title="下載此檔案"
                                                        >
                                                            <FaDownload size={12} />
                                                        </button>
                                                    </div>
                                                ))
                                            ) : (
                                                <span className="text-xs text-gray-400 italic">無檔案</span>
                                            )}
                                        </div>
                                    </td>

                                    {/* Submitted at */}
                                    <td className="px-4 py-3 text-gray-600">
                                        {formatDate(sub.submitted_at)}
                                    </td>

                                    {/* Score */}
                                    <td className="px-4 py-3 text-center">
                                        {editingId === sub.id ? (
                                            <div className="flex items-center justify-center gap-1">
                                                <input
                                                    type="number"
                                                    min="0"
                                                    max={totalPoints}
                                                    step="0.5"
                                                    value={editScore}
                                                    onChange={(e) => setEditScore(e.target.value)}
                                                    className="w-16 px-2 py-1 border border-blue-300 rounded text-center text-sm focus:ring-2 focus:ring-blue-400 outline-none"
                                                    autoFocus
                                                />
                                                <span className="text-xs text-gray-400">/ {totalPoints}</span>
                                            </div>
                                        ) : (
                                            sub.score !== null ? (
                                                <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-green-50 text-green-700 rounded-full font-semibold text-xs">
                                                    <FaCheckCircle className="text-green-500" />
                                                    {sub.score} / {totalPoints}
                                                </span>
                                            ) : (
                                                <span className="text-gray-400 text-xs">未評分</span>
                                            )
                                        )}
                                    </td>

                                    {/* Actions */}
                                    <td className="px-4 py-3">
                                        <div className="flex items-center justify-center gap-2">
                                            {/* Legacy single download (Downloads first file) */}
                                            {sub.files && sub.files.length > 1 && (
                                                <div className="text-[10px] text-gray-400 italic">多檔案可分開下載</div>
                                            )}

                                            {/* Grade */}
                                            {editingId === sub.id ? (
                                                <>
                                                    <button
                                                        onClick={() => handleSaveGrade(sub.id)}
                                                        disabled={saving}
                                                        className="p-2 text-green-600 hover:bg-green-50 rounded-lg transition-all disabled:opacity-50"
                                                        title="儲存分數"
                                                    >
                                                        {saving ? <FaSpinner className="animate-spin" /> : <FaSave />}
                                                    </button>
                                                    <button
                                                        onClick={cancelEditing}
                                                        className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-all"
                                                        title="取消"
                                                    >
                                                        <FaTimes />
                                                    </button>
                                                </>
                                            ) : (
                                                <button
                                                    onClick={() => startEditing(sub)}
                                                    className="p-2 text-gray-500 hover:text-orange-600 hover:bg-orange-50 rounded-lg transition-all"
                                                    title="評分"
                                                >
                                                    <FaPen />
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Feedback editing area (when editing) */}
            {editingId && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
                    <label className="block text-sm font-medium text-blue-800 mb-2">
                        <FaStar className="inline mr-1" />
                        評語 / 回饋
                    </label>
                    <textarea
                        className="w-full px-4 py-3 border border-blue-200 rounded-lg text-sm resize-y min-h-[80px] focus:ring-2 focus:ring-blue-400 outline-none bg-white"
                        placeholder="輸入對此學生的回饋..."
                        value={editFeedback}
                        onChange={(e) => setEditFeedback(e.target.value)}
                    />
                </div>
            )}
        </div>
    );
}
