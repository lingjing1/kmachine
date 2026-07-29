/**
 * Teacher Kappa Evaluation API client
 *
 * 四個任務：
 * - course62_mastery       (Task A)
 * - course62_polarity      (Task B)
 * - finetune_mastery       (Task C1)
 * - finetune_performance   (Task C2)
 *
 * 所有請求自動注入 JWT；後端白名單 = {34, 6}。
 */
import API_BASE_URL from '../config/api';

const BASE = `${API_BASE_URL}/api/teacher/kappa-eval`;

// ==================== Types ====================
export type TaskName =
    | 'course62_mastery'
    | 'course62_polarity'
    | 'finetune_mastery'
    | 'finetune_performance';

export interface TaskProgress {
    task: TaskName;
    total: number;
    completed: number;
}

export interface OverviewResponse {
    teacher_id: number;
    tasks: TaskProgress[];
}

export interface SampleListItem {
    id: number;
    display_order: number;
    stratum: string;
    is_completed: boolean;
    submitted_at: string | null;
}

export interface SampleListResponse {
    task: TaskName;
    total: number;
    completed: number;
    items: SampleListItem[];
}

// ---------- Task A: course62 mastery ----------
export interface LimeReportJSON {
    keywords?: string[];
    bert_input?: string;
    prediction?: string;
    bert_output?: {
        fallback?: boolean;
        confidence?: number;
        prediction?: string;
        prediction_id?: number;
        probabilities?: Record<string, number>;
    };
    generated_at?: string;
    mastery_level?: string;
    feature_weights?: Record<string, number>;
    highlighted_text?: {
        original: string;
        highlights: Array<{
            start: number;
            end: number;
            weight: number;
            keyword: string;
        }>;
    };
}

export interface Course62MasterySample {
    id: number;
    display_order: number;
    stratum: string;
    ai_mastery: string;
    ai_mastery_confidence: number | null;
    lime_report_json: LimeReportJSON;
    teacher_mastery: string | null;
    teacher_note: string | null;
    submitted_at: string | null;
}

export interface Course62MasterySubmit {
    teacher_mastery: string;
    teacher_note?: string | null;
}

// ---------- Task B: course62 polarity ----------
export interface PolarityItem {
    keyword: string;
    weight: number;
    polarity: '+' | '-';
    is_meta: boolean;
}

export interface TeacherPolarityItem {
    keyword: string;
    polarity: '+' | '-';
}

export interface Course62PolaritySample {
    id: number;
    display_order: number;
    stratum: string;
    lime_report_json: LimeReportJSON;
    ai_polarities: PolarityItem[];
    teacher_polarities: TeacherPolarityItem[] | null;
    teacher_note: string | null;
    submitted_at: string | null;
}

export interface Course62PolaritySubmit {
    teacher_polarities: TeacherPolarityItem[];
    teacher_note?: string | null;
}

// ---------- Task C1: finetune mastery ----------
export interface FinetuneMasterySample {
    id: number;
    display_order: number;
    stratum: string;
    csv_row: Record<string, any>;
    ai_mastery: string;
    teacher_mastery: string | null;
    teacher_note: string | null;
    submitted_at: string | null;
}

export interface FinetuneMasterySubmit {
    teacher_mastery: string;
    teacher_note?: string | null;
}

// ---------- Task C2: finetune performance ----------
export interface FinetunePerformanceSample {
    id: number;
    display_order: number;
    stratum: string;
    question_snapshot: {
        csv_row_idx: number;
        q_idx_in_row: number;
        chapter?: string | null;
        section?: string | null;
        question: string;
        reference_answer: string;
        student_answer: string;
    };
    ai_performance: string;
    teacher_performance: string | null;
    teacher_note: string | null;
    submitted_at: string | null;
}

export interface FinetunePerformanceSubmit {
    teacher_performance: string;
    teacher_note?: string | null;
}

// ==================== HTTP helper ====================
// 自動注入 JWT，與專案既有 authClient 相容
async function authFetch<T>(url: string, init?: RequestInit): Promise<T> {
    const token = sessionStorage.getItem('access_token');
    const headers: HeadersInit = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers || {}),
    };
    const res = await fetch(url, { ...init, headers });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const err = new Error(data.detail || `HTTP ${res.status}`) as any;
        err.status = res.status;
        throw err;
    }
    return res.json();
}

// ==================== Overview ====================
export const getOverview = () =>
    authFetch<OverviewResponse>(`${BASE}/overview`);

// ==================== Task A ====================
export const listCourse62Mastery = () =>
    authFetch<SampleListResponse>(`${BASE}/course62-mastery/samples`);

export const getCourse62Mastery = (id: number) =>
    authFetch<Course62MasterySample>(`${BASE}/course62-mastery/samples/${id}`);

export const submitCourse62Mastery = (id: number, payload: Course62MasterySubmit) =>
    authFetch<Course62MasterySample>(`${BASE}/course62-mastery/samples/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
    });

// ==================== Task B ====================
export const listCourse62Polarity = () =>
    authFetch<SampleListResponse>(`${BASE}/course62-polarity/samples`);

export const getCourse62Polarity = (id: number) =>
    authFetch<Course62PolaritySample>(`${BASE}/course62-polarity/samples/${id}`);

export const submitCourse62Polarity = (id: number, payload: Course62PolaritySubmit) =>
    authFetch<Course62PolaritySample>(`${BASE}/course62-polarity/samples/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
    });

// ==================== Task C1 ====================
export const listFinetuneMastery = () =>
    authFetch<SampleListResponse>(`${BASE}/finetune-mastery/samples`);

export const getFinetuneMastery = (id: number) =>
    authFetch<FinetuneMasterySample>(`${BASE}/finetune-mastery/samples/${id}`);

export const submitFinetuneMastery = (id: number, payload: FinetuneMasterySubmit) =>
    authFetch<FinetuneMasterySample>(`${BASE}/finetune-mastery/samples/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
    });

// ==================== Task C2 ====================
export const listFinetunePerformance = () =>
    authFetch<SampleListResponse>(`${BASE}/finetune-performance/samples`);

export const getFinetunePerformance = (id: number) =>
    authFetch<FinetunePerformanceSample>(`${BASE}/finetune-performance/samples/${id}`);

export const submitFinetunePerformance = (id: number, payload: FinetunePerformanceSubmit) =>
    authFetch<FinetunePerformanceSample>(`${BASE}/finetune-performance/samples/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
    });

// ==================== 白名單 helper ====================
export const KAPPA_EVAL_WHITELIST = new Set<number>([34, 6]);
export const isAllowedForKappaEval = (userId: number | undefined | null): boolean =>
    userId != null && KAPPA_EVAL_WHITELIST.has(userId);
