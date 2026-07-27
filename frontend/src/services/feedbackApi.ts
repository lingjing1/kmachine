import { authClient } from './authClient';

export interface FAQItem {
    id: number;
    question: string;
    answer: string;
    role: string;
    category: string;
}

export interface ProblemType {
    id: string;
    label: string;
    category: string;
}

export interface FeedbackConfig {
    faqs: FAQItem[];
    problem_types: ProblemType[];
}

export interface FeedbackReportRequest {
    selected_problems: string[] | null;
    description: string;
}

/**
 * 取得回饋中心配置 (FAQ 與 問題類型)
 */
export const getFeedbackConfig = async (): Promise<FeedbackConfig> => {
    return authClient.get<FeedbackConfig>('/api/feedback/config');
};

/**
 * 提交回饋報告
 */
export const submitFeedbackReport = async (data: FeedbackReportRequest): Promise<{ status: string; message: string }> => {
    return authClient.post<{ status: string; message: string }>('/api/feedback/report', data);
};
