import { authClient } from './authClient';

export interface TeacherRatingRequest {
    rating: number;
    feedback?: string;
    dimensions?: Record<string, any>;
}

export interface TeacherRatingResponse {
    id: number;
    teacher_rating: {
        score: number;
        feedback?: string;
        dimensions?: Record<string, any>;
    };
    updated_at: string;
}

export interface RatingStatsResponse {
    total_count: number;
    suggest_detailed: boolean;
}

/**
 * 提交或更新教師對生成內容的評分
 */
export async function submitTeacherRating(
    contentId: number,
    data: TeacherRatingRequest
): Promise<TeacherRatingResponse> {
    return authClient.post(`/api/v1/teacher/generated_contents/${contentId}/rate`, data);
}

/**
 * 取得教師評分統計
 */
export async function getTeacherRatingStats(): Promise<RatingStatsResponse> {
    return authClient.get(`/api/v1/teacher/stats/rating_count`);
}
