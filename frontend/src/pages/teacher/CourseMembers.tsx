import { useState, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FaSearch, FaUserShield, FaUserGraduate, FaDownload, FaChalkboardTeacher } from 'react-icons/fa';
import { HiOutlineUserGroup } from 'react-icons/hi2';
import { authClient } from '../../services/authClient';
import Spinner from '../../components/common/Spinner';
import Toast from '../../components/common/Toast';
import ConfirmDialog from '../../components/common/ConfirmDialog';
import { useUser } from '../../contexts/UserContext';

interface CourseMember {
    user_id: number;
    full_name: string;
    email: string;
    student_id?: string;
    department?: string;
    enrollment_role: 'student' | 'ta';
    enrolled_at: string;
}

interface CourseDetail {
    id: number;
    name: string;
    semester: string;
    description: string;
    teacher_name: string;
    teacher_email?: string;
    teacher_department?: string;
}

const CourseMembersPage = () => {
    const { courseId } = useParams<{ courseId: string }>();
    const { user } = useUser();
    const queryClient = useQueryClient();
    const [searchTerm, setSearchTerm] = useState('');
    const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'error' | 'info' }>({ show: false, message: '', type: 'success' });
    const [confirmDelete, setConfirmDelete] = useState<{ show: boolean; userId: number | null; userName: string }>({ show: false, userId: null, userName: '' });

    const isTeacher = user?.role === 'teacher' || user?.role === 'admin';

    const { data: members = [], isLoading: isLoadingMembers, error: membersError } = useQuery<CourseMember[]>({
        queryKey: ['course-members', courseId],
        queryFn: () => authClient.get(`/api/teacher/courses/${courseId}/members`),
        enabled: !!courseId,
    });

    // Fetch course details for teacher name
    const { data: course, isLoading: isLoadingCourse } = useQuery<CourseDetail>({
        queryKey: ['course-detail', courseId],
        queryFn: () => authClient.get(`/api/courses/${courseId}`),
        enabled: !!courseId,
    });

    const isLoading = isLoadingMembers || isLoadingCourse;
    const error = membersError;

    // Promote to TA
    const promoteMutation = useMutation({
        mutationFn: (targetUserId: number) =>
            authClient.request(`/api/teacher/courses/${courseId}/members/${targetUserId}/promote-ta`, { method: 'PATCH' }),
        onSuccess: () => {
            setToast({ show: true, message: '已設為助教', type: 'success' });
            queryClient.invalidateQueries({ queryKey: ['course-members', courseId] });
        },
        onError: (err: any) => {
            setToast({ show: true, message: err?.detail || '設定失敗', type: 'error' });
        },
    });

    // Demote to student
    const demoteMutation = useMutation({
        mutationFn: (targetUserId: number) =>
            authClient.request(`/api/teacher/courses/${courseId}/members/${targetUserId}/demote-student`, { method: 'PATCH' }),
        onSuccess: () => {
            setToast({ show: true, message: '已還原為學生', type: 'success' });
            queryClient.invalidateQueries({ queryKey: ['course-members', courseId] });
        },
        onError: (err: any) => {
            setToast({ show: true, message: err?.detail || '操作失敗', type: 'error' });
        },
    });

    // Remove member
    const removeMutation = useMutation({
        mutationFn: (targetUserId: number) =>
            authClient.request(`/api/teacher/courses/${courseId}/members/${targetUserId}`, { method: 'DELETE' }),
        onSuccess: () => {
            setToast({ show: true, message: '已將成員移除課堂', type: 'success' });
            setConfirmDelete({ show: false, userId: null, userName: '' });
            queryClient.invalidateQueries({ queryKey: ['course-members', courseId] });
        },
        onError: (err: any) => {
            setToast({ show: true, message: err?.detail || '移除失敗', type: 'error' });
            setConfirmDelete({ show: false, userId: null, userName: '' });
        },
    });

    const filteredMembers = useMemo(() => {
        if (!searchTerm) return members;
        const lower = searchTerm.toLowerCase();
        return members.filter(m =>
            m.full_name.toLowerCase().includes(lower) ||
            m.email.toLowerCase().includes(lower) ||
            (m.student_id && m.student_id.toLowerCase().includes(lower)) ||
            (m.department && m.department.toLowerCase().includes(lower))
        );
    }, [members, searchTerm]);

    const taCount = members.filter(m => m.enrollment_role === 'ta').length;
    const studentCount = members.filter(m => m.enrollment_role === 'student').length;

    const isActioning = (userId: number) =>
        (promoteMutation.isPending && promoteMutation.variables === userId) ||
        (demoteMutation.isPending && demoteMutation.variables === userId) ||
        (removeMutation.isPending && removeMutation.variables === userId);

    const currentUserRoleInCourse = members.find(m => m.user_id === user?.user_id)?.enrollment_role;
    const canManage = isTeacher || currentUserRoleInCourse === 'ta';

    const handleExportCSV = () => {
        if (!members || members.length === 0) {
            setToast({ show: true, message: '目前無成員資料可供匯出', type: 'info' });
            return;
        }

        // CSV Headers
        const headers = ['姓名', '學號', 'Email', '科系', '加入時間', '身份'];

        // CSV Rows
        const rows = members.map(member => [
            member.full_name,
            member.student_id || '',
            member.email,
            member.department || '',
            new Date(member.enrolled_at).toLocaleDateString('zh-TW'),
            member.enrollment_role === 'ta' ? '助教' : '學生'
        ]);

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
        link.setAttribute('download', `${course?.name || '課程'}_成員名單_${dateStr}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setToast({ show: true, message: '成員名單匯出成功', type: 'success' });
    };

    if (isLoading) return <div className="flex justify-center items-center h-screen"><Spinner /></div>;
    if (error) return <div className="p-8 text-red-500">無法載入成員資料</div>;

    return (
        <div className="container mx-auto px-4 py-8 max-w-[1200px]">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-8">
                <div className="flex items-center gap-4 flex-1">
                    <HiOutlineUserGroup className="text-blue-600 text-4xl shrink-0" />
                    <div className="min-w-0">
                        <h1 className="text-3xl font-bold text-gray-800">
                            成員管理
                        </h1>
                        <p className="text-gray-500 font-medium truncate">
                            {course?.name ? `目前課程：${course.name}` : '載入課程資訊中...'}
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-3 shrink-0 flex-wrap md:flex-nowrap">
                    {/* Teacher Info Badge - Lighter Background, Deep Blue Text */}
                    <div className="flex items-center gap-2 bg-blue-50 text-blue-900 px-4 py-2 rounded-xl border border-blue-100 font-medium whitespace-nowrap shadow-sm">
                        <FaChalkboardTeacher className="text-blue-600" />
                        <span>授課教師：{course?.teacher_name || '...'}</span>
                        {course?.teacher_department && (
                            <span className="text-blue-700 text-xs border-l border-blue-200 pl-2 ml-1">{course.teacher_department}</span>
                        )}
                        {course?.teacher_email && (
                            <span className="text-blue-600 text-xs border-l border-blue-200 pl-2 ml-1 font-normal italic">{course.teacher_email}</span>
                        )}
                    </div>

                    <div className="flex items-center gap-2 bg-blue-50 text-blue-700 px-4 py-2 rounded-xl border border-blue-100 font-medium whitespace-nowrap">
                        <FaUserGraduate className="text-blue-500" />
                        學生 {studentCount} 人
                    </div>
                    <div className="flex items-center gap-2 bg-purple-50 text-purple-700 px-4 py-2 rounded-xl border border-purple-100 font-medium whitespace-nowrap">
                        <FaUserShield className="text-purple-500" />
                        助教 {taCount} 人
                    </div>
                    <button
                        onClick={handleExportCSV}
                        className="flex items-center gap-2 bg-white text-gray-700 px-4 py-2 rounded-xl border border-gray-200 hover:bg-gray-50 transition-all font-medium shadow-sm whitespace-nowrap"
                    >
                        <FaDownload className="text-gray-400" />
                        匯出
                    </button>
                </div>
            </div>

            {/* Search */}
            <div className="relative mb-8">
                <FaSearch className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                    type="text"
                    placeholder="搜尋姓名、學號、信箱或科系..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full pl-12 pr-4 py-3 bg-white border border-gray-200 rounded-2xl focus:ring-4 focus:ring-blue-500/5 focus:border-blue-500 outline-none transition-all text-sm shadow-sm"
                />
            </div>

            {/* Table */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
                <div className="overflow-x-auto custom-scrollbar">
                    <table className="w-full border-collapse text-sm">
                        <thead>
                            <tr className="bg-gray-50 border-b border-gray-200">
                                <th className="px-6 py-4 text-left font-bold text-gray-700 min-w-[200px]">
                                    姓名
                                    <div className="text-xs font-normal text-gray-400 mt-0.5">共 {filteredMembers.length} 人</div>
                                </th>
                                <th className="px-6 py-4 text-left font-bold text-gray-700">學號</th>
                                <th className="px-6 py-4 text-left font-bold text-gray-700">Email</th>
                                <th className="px-6 py-4 text-left font-bold text-gray-700">科系</th>
                                <th className="px-6 py-4 text-left font-bold text-gray-700">加入時間</th>
                                <th className="px-6 py-4 text-center font-bold text-gray-700">身份</th>
                                {canManage && (
                                    <th className="px-6 py-4 text-center font-bold text-gray-700">操作</th>
                                )}
                            </tr>
                        </thead>
                        <tbody>
                            {filteredMembers.length === 0 ? (
                                <tr>
                                    <td colSpan={canManage ? 7 : 6} className="px-6 py-12 text-center text-gray-400">
                                        {searchTerm ? '找不到符合條件的成員' : '此課程尚無成員'}
                                    </td>
                                </tr>
                            ) : (
                                filteredMembers.map((member) => (
                                    <tr
                                        key={member.user_id}
                                        className="border-b border-gray-100 last:border-b-0 hover:bg-gray-50/50 transition-colors"
                                    >
                                        {/* Name + avatar */}
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-3">
                                                <div className={`w-9 h-9 rounded-full flex items-center justify-center text-white font-bold text-sm flex-shrink-0 shadow-sm ${member.enrollment_role === 'ta' ? 'bg-gradient-to-br from-purple-500 to-violet-600' : 'bg-gradient-to-br from-blue-500 to-indigo-600'}`}>
                                                    {member.full_name.charAt(0)}
                                                </div>
                                                <span className="font-semibold text-gray-800">{member.full_name}</span>
                                            </div>
                                        </td>

                                        {/* Student ID */}
                                        <td className="px-6 py-4 text-gray-600 font-mono text-xs">
                                            {member.student_id || <span className="text-gray-300 italic">—</span>}
                                        </td>

                                        {/* Email */}
                                        <td className="px-6 py-4 text-gray-500 text-xs">
                                            <a href={`mailto:${member.email}`} className="hover:text-blue-600 hover:underline transition-colors">
                                                {member.email}
                                            </a>
                                        </td>

                                        {/* Department */}
                                        <td className="px-6 py-4 text-gray-600 text-xs">
                                            {member.department || <span className="text-gray-300 italic">—</span>}
                                        </td>

                                        {/* Enrolled at */}
                                        <td className="px-6 py-4 text-gray-400 text-xs whitespace-nowrap">
                                            {new Date(member.enrolled_at).toLocaleDateString('zh-TW')}
                                        </td>

                                        {/* Role badge */}
                                        <td className="px-6 py-4 text-center">
                                            {member.enrollment_role === 'ta' ? (
                                                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-purple-100 text-purple-700 border border-purple-200">
                                                    <FaUserShield size={10} /> 助教
                                                </span>
                                            ) : (
                                                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-600 border border-blue-100">
                                                    <FaUserGraduate size={10} /> 學生
                                                </span>
                                            )}
                                        </td>

                                        {/* Actions */}
                                        {canManage && (
                                            <td className="px-6 py-4 text-center whitespace-nowrap">
                                                {isActioning(member.user_id) ? (
                                                    <div className="flex justify-center">
                                                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-amber-500" />
                                                    </div>
                                                ) : member.user_id === user?.user_id ? (
                                                    <span className="text-xs text-gray-400 italic">本人</span>
                                                ) : (
                                                    <div className="flex items-center justify-center gap-2">
                                                        {isTeacher && member.enrollment_role === 'ta' && (
                                                            <button
                                                                onClick={() => demoteMutation.mutate(member.user_id)}
                                                                className="text-xs px-2 py-1 rounded-lg border border-gray-200 text-gray-500 hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-all"
                                                            >
                                                                取消助教
                                                            </button>
                                                        )}
                                                        {isTeacher && member.enrollment_role === 'student' && (
                                                            <button
                                                                onClick={() => promoteMutation.mutate(member.user_id)}
                                                                className="text-xs px-2 py-1 rounded-lg border border-purple-200 text-purple-600 bg-purple-50 hover:bg-purple-100 transition-all font-medium"
                                                            >
                                                                設為助教
                                                            </button>
                                                        )}
                                                        {/* Remove button: Visible to Teacher always, visible to TA for students only */}
                                                        {(isTeacher || (currentUserRoleInCourse === 'ta' && member.enrollment_role === 'student')) && (
                                                            <button
                                                                onClick={() => setConfirmDelete({ show: true, userId: member.user_id, userName: member.full_name })}
                                                                className="text-xs px-2 py-1 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 transition-all"
                                                            >
                                                                移除
                                                            </button>
                                                        )}
                                                    </div>
                                                )}
                                            </td>
                                        )}
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Footer */}
                <div className="bg-gray-50 px-6 py-3 border-t border-gray-200 flex justify-between items-center text-xs text-gray-500">
                    <span>顯示 {filteredMembers.length} / {members.length} 人</span>
                    <span>共 {taCount} 位助教 · {studentCount} 位學生</span>
                </div>
            </div>

            {toast.show && (
                <Toast
                    message={toast.message}
                    type={toast.type}
                    onClose={() => setToast(prev => ({ ...prev, show: false }))}
                />
            )}

            {confirmDelete.show && (
                <ConfirmDialog
                    isOpen={confirmDelete.show}
                    title="移除成員"
                    message={`確定要把 ${confirmDelete.userName} 從課堂中移除嗎？此操作將會刪除該學生的修課記錄。`}
                    onConfirm={() => confirmDelete.userId && removeMutation.mutate(confirmDelete.userId)}
                    onCancel={() => setConfirmDelete({ show: false, userId: null, userName: '' })}
                    confirmText="確定移除"
                    cancelText="取消"
                    variant="danger"
                />
            )}
        </div>
    );
};

export default CourseMembersPage;
