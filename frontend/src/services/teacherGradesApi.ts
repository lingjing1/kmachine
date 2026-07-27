import { authClient } from './authClient';  // ✅ Phase 4: JWT 認證

export interface SubmissionInfo {
    content_id: number;
    content_title: string;
    content_type: string;
    content_subtype: string | null;
    total_points: number;
    weight: number;
    score: number | null;
    percentage: number | null;
    grade: any | null;
    files: any[] | null;
    id: number | null;
    submitted_at: string | null;
    updated_at: string | null;
    is_manual: boolean;
}

export interface StudentGradeInfo {
    user_id: number;
    full_name: string;
    email: string;
    student_id: string | null;
    major: string | null;
    role?: string;
    submissions: SubmissionInfo[];
    weighted_score: number;
    total_percentage: number;
}

export interface ContentInfo {
    content_id: number;
    title: string;
    content_type: string;
    content_subtype: string | null;
    total_points: number;
    weight: number;
    include_in_grade: boolean;
    avg_score: number | null;
    avg_percentage: number | null;
    submission_count: number;
    total_students: number;
}

export interface GradeOverviewResponse {
    students: StudentGradeInfo[];
    contents: ContentInfo[];
    total_weight: number;
    weight_valid: boolean;
}

export interface WeightUpdateItem {
    content_id: number;
    weight: number;
}

export interface UpdateSubmissionGradeItem {
    content_id: number;
    user_id: number;
    score: number;
    grade: any;
}

export const getCourseGrades = async (courseId: string | number, includePractice: boolean = false): Promise<GradeOverviewResponse> => {
    // ✅ Phase 4: 使用 authClient
    return authClient.get(`/api/teacher/courses/${courseId}/grades`, { include_practice: includePractice });
};

export const updateGradeWeights = async (courseId: string | number, weights: WeightUpdateItem[]) => {
    // ✅ Phase 4: 使用 authClient
    return authClient.put(`/api/teacher/courses/${courseId}/grades/weights`, { weights });
};
export const updateSubmissionGrade = async (courseId: string | number, payload: UpdateSubmissionGradeItem) => {
    // ✅ Phase 4: 使用 authClient
    return authClient.put(`/api/teacher/courses/${courseId}/grades/submissions`, payload);
};
