import { authClient } from './authClient';

export interface CourseStaffInfo {
    full_name: string;
    email: string;
    role: string;
}

export interface StudentGradeItem {
    sub_id?: number;
    content_id: number;
    title: string;
    content_type: string;
    content_subtype?: string;
    total_points: number;
    weight: number;
    score?: number;
    percentage?: number;
    grade?: any;
    files: any[] | null;
    submitted_at: string | null;
    start_time: string | null;
    is_manual: boolean;
}

export interface StudentGradeOverviewResponse {
    course_name: string;
    staff: CourseStaffInfo[];
    grades: StudentGradeItem[];
    weighted_total: number;
    total_scored_weight: number;
}

export const studentGradesApi = {
    /**
     * 獲取學生個人成績概覽
     */
    getMyGrades: (courseId: number): Promise<StudentGradeOverviewResponse> => {
        return authClient.get(`/api/v1/student/courses/${courseId}/grades`);
    }
};
