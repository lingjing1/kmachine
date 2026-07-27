import { authClient } from './authClient';

// --- Types ---

export interface KnowledgePointMastery {
    id: number;
    name: string;
    mastered: number; // Percentage
    moderate: number; // Percentage
    weak: number;     // Percentage
}

export interface OverviewSummary {
    total_students: number;
    preview_completion_rate: number;
    review_completion_rate: number;
    preview_count: number;
    review_count: number;
}

export interface DashboardData {
    summary: OverviewSummary;
    knowledge_points: KnowledgePointMastery[];
    ai_analysis?: {
        content: string;
        suggestions: string[];
    };
}

export interface WeakPointInfo {
    kp_id: number;
    kp_name: string;
    weak_count: number;
    student_count: number;
    status: string;
}

export interface AtRiskStudent {
    id: number;
    student_id: string; // e.g. "S006"
    name: string;
    status: string;
    weak_points_count: number;
    weak_knowledge_points: string[];
}

// --- API Functions ---

export const getDashboardOverview = async (unitId: number | string, stage: string = 'preview'): Promise<DashboardData> => {
    return authClient.get(`/api/v1/teacher/dashboard/overview`, {
        unit_id: unitId,
        stage: stage
    });
};

export const getAtRiskStudents = async (unitId: number | string, stage: string = 'preview', riskThreshold: number = 2, showAll: boolean = false): Promise<AtRiskStudent[]> => {
    return authClient.get(`/api/v1/teacher/dashboard/students`, {
        unit_id: unitId,
        stage: stage,
        risk_threshold: riskThreshold,
        show_all: showAll
    });
};

export const getClassWeakPoints = async (unitId: number | string, stage: string = 'preview'): Promise<WeakPointInfo[]> => {
    return authClient.get(`/api/v1/teacher/dashboard/weak-points`, {
        unit_id: unitId,
        stage: stage
    });
};
