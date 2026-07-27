import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { useUser } from '../../contexts/UserContext';
import API_BASE_URL from '../../config/api';
import Spinner from '../../components/common/Spinner';
import CreateCourseModal from './CreateCourseModal';

function TeacherDashboard() {
    const { user } = useUser();
    const queryClient = useQueryClient();
    const [targetPath, setTargetPath] = useState<string | null>(null);
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

    const { data: courses = [], isLoading } = useQuery({
        queryKey: ['courses', 'teacher', user?.user_id],
        queryFn: async () => {
            if (!user?.user_id) return [];
            const response = await fetch(`${API_BASE_URL}/api/teachers/${user.user_id}/courses`);
            if (!response.ok) throw new Error('Failed to fetch courses');
            return response.json();
        },
        enabled: !!user?.user_id,
        staleTime: 5 * 60 * 1000,
    });

    useEffect(() => {
        if (!isLoading && courses.length > 0) {
            setTargetPath(`/teacher/courses/${courses[0].id}`);
        }
    }, [isLoading, courses]);

    const handleCourseCreated = (courseId: number) => {
        queryClient.invalidateQueries({ queryKey: ['courses', 'teacher', user?.user_id] });
        setTargetPath(`/teacher/courses/${courseId}`);
    };

    if (targetPath) {
        return <Navigate to={targetPath} replace />;
    }

    if (isLoading) {
        return (
            <div className="flex h-full items-center justify-center">
                <Spinner />
            </div>
        );
    }

    return (
        <div className="flex h-full flex-col items-center justify-center text-neutral-text-secondary">
            <h2 className="text-xl font-semibold mb-2">歡迎回來，{user?.full_name}教師</h2>
            <p>您目前沒有開設任何課程。</p>
            <button
                onClick={() => setIsCreateModalOpen(true)}
                className="mt-4 px-4 py-2 bg-theme-primary text-white rounded-lg hover:bg-theme-primary-hover transition-colors"
            >
                建立新課程
            </button>

            <CreateCourseModal
                isOpen={isCreateModalOpen}
                onClose={() => setIsCreateModalOpen(false)}
                onSuccess={handleCourseCreated}
            />
        </div>
    );
}

export default TeacherDashboard;
