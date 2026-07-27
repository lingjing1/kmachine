/**
 * Student API Service
 * 
 * 封裝所有學生端後端 API 調用
 */

import { authClient } from './authClient';  // ✅ Phase 4: JWT 認證

import API_BASE_URL from '../config/api';

// ==================== Type Definitions ====================

export interface PreviewContentResponse {
    knowledge_point_id: number;
    knowledge_point_name: string;
    unit_name: string;
    content_markdown: string;
    content_plain?: string;
    created_at: string;
}

export interface QuestionItem {
    id: number;
    question: string;
    question_text?: string; // Database uses this field name
    type?: string; // 'multiple_choice', 'short_answer', etc.
    question_type?: string; // Alternative field name
    options?: Record<string, string>; // For multiple choice: {A: "...", B: "...", ...}
    correct_answer?: string; // For multiple choice: "A", "B", etc.
    reference_pages?: string;
    question_number?: number;
    source?: any; // Source metadata
}

export interface QuestionsResponse {
    knowledge_point_id: number;
    knowledge_point_name: string;
    questions: QuestionItem[];
}

export interface QuestionLogRequest {
    question_id?: number;  // Optional for inline questions
    knowledge_point_id: number;
    stage: 'preview' | 'review';
    answer: string;
    question_type?: string;  // 'multiple_choice' | 'short_answer' | 'true_false'
    correct_answer?: string;  // For multiple choice auto-grading
    question_text?: string;  // For inline questions (not in question_bank)
    detailed_explanation?: string; // Static explanation for the question
    unit_session_id?: string; // [NEW] 學習路徑 Session ID
}

// Submission interfaces (for assignments and exams)
export interface QuestionAnswer {
    question_text: string;
    question_type: string;  // 'multiple_choice' | 'short_answer' | 'true_false'
    student_answer: string;
    correct_answer?: string;  // For multiple_choice/true_false
    reference_answer?: string;  // For short_answer
    detailed_explanation?: string; // Static explanation for the question
}

export interface SubmissionRequest {
    answers: QuestionAnswer[];
    started_at?: string;  // ISO format timestamp (for exams)
    unit_session_id?: string; // [NEW] 學習路徑 Session ID
}

export interface QuestionResult {
    question_text: string;
    question_type: string;
    student_answer: string;
    correctness: string;  // 'correct' | 'incorrect' | 'partially_correct'
    feedback: string;
    explanation?: string;
}

export interface SubmissionResponse {
    submission_id: number;
    grade?: number;
    score?: number;
    percentage?: number;
    feedback?: string;
    is_manual: boolean;
    results: QuestionResult[];
}

export interface QuestionLogResponse {
    log_id: number;
    status: string;
    message: string;
}

export interface BatchEvaluateRequest {
    log_ids: number[];
}

export interface EvaluationResult {
    log_id: number;
    question_id: number;
    correctness: string;
    feedback: string;
    explanation?: string;
    evaluated_at: string;
}

export interface BatchEvaluateResponse {
    results: EvaluationResult[];
    summary: Record<string, any>;
}

// ==================== Challenge Log Types ====================

export interface ChallengeAnswerItem {
    question_id: number;
    knowledge_point_id: number;
    answer: string;
    difficulty_level?: string;
    question_type?: string;
    question_text?: string;
}

export interface SubmitChallengesRequest {
    answers: ChallengeAnswerItem[];
    unit_session_id?: string; // [NEW] 學習路徑 Session ID
}

export interface ChallengeEvaluationResult {
    log_id: number;
    question_id: number;
    correctness: string;
    feedback: string;
    explanation?: string;
    evaluated_at: string;
}

export interface SubmitChallengesResponse {
    results: ChallengeEvaluationResult[];
    summary: {
        total: number;
        correct: number;
        partially_correct: number;
        incorrect: number;
    };
}

export interface ChallengeHistoryItem {
    log_id: number;
    question_id: number;
    answer: string;
    correctness?: string;
    feedback?: string;
    explanation?: string;
    answered_at?: string;
}

// ==================== Recommended Questions Types ====================

export interface RecommendedQuestionItem {
    id: number;
    question: string;
    question_type: string;
    knowledge_point_id: number;
    knowledge_point_name: string;
    reference_pages?: string;
    difficulty_level?: string;
    detailed_explanation?: string;
    options?: Record<string, string>;
    correct_answer?: string;
    source?: any;
    sample_answer?: string;
    answer?: string;
    tags?: string[];
}

export interface RecommendedQuestionsResponse {
    questions: RecommendedQuestionItem[];
    total_count: number;
}

export interface MasteryEvaluateRequest {
    stage: 'preview' | 'review';
    unit_session_id?: string;
}

export interface MasteryEvaluateResponse {
    knowledge_point_id: number;
    knowledge_point_name: string;
    mastery_level: string;  // "精熟" | "尚可" | "待加強"
    confidence_score: number;
    evaluated_at: string;
    summary: {
        total_questions: number;
        correct: number;
        partially_correct: number;
        incorrect: number;
        correct_rate: number;
        has_dialog: boolean;
        lime_report_generated: boolean;
        lime_report_path?: string;
    };
}

// ==================== Attachment Viewer Types ====================

export interface PPTXSlide {
    slide_index: number;
    texts: string[];
    images: {
        content: string; // Base64
        content_type: string;
    }[];
}

export interface AttachmentViewResponse {
    type: 'html' | 'pptx' | 'pdf' | 'text' | 'image' | 'download';
    content: string | PPTXSlide[];
    mime?: string;          // 圖片類型用 (e.g. 'image/png')
    download_url?: string;  // 不支援預覽格式用
}

export interface SendMessageRequest {
    conversation_id?: string;
    message: string;
    course_id: number;
    unit_id: number;
    knowledge_point_id?: number;
    attachment_id?: number;   // AttachmentViewer: 附件閱讀場景
    content_id?: number;      // TopicPreview: 預習/複習教材場景
    student_id?: number;
    unit_session_id?: string; // [NEW] 學習路徑 Session ID
}

export interface SourceItem {
    chunk_id: number;
    title?: string;
    section?: string;
    snippet?: string;
    page_numbers?: string;
    source_filename?: string;
    locator?: string;
    // New RAG fields
    unit_name?: string;
    knowledge_point_name?: string;
    original_score?: number;
    rerank_score?: number;
    boosted?: boolean;
}

export interface SendMessageResponse {
    conversation_id: string;
    user_message_id: number;
    assistant_message_id: number;
    assistant_response: string;
    sources?: SourceItem[];
    metadata?: Record<string, any>;
}

// ==================== Conversation History Types ====================
// 對應後端 backend/app/routers/student_chatbot_router.py 的
// ConversationSummary / GetConversationsResponse / DialogMessage / GetConversationHistoryResponse

export interface ConversationSummary {
    conversation_id: string;
    first_message: string;
    last_message_at: string;
    message_count: number;
    unit_id?: number;
    knowledge_point_id?: number;
}

export interface GetConversationsResponse {
    conversations: ConversationSummary[];
    total_count: number;
}

export interface DialogMessage {
    id: number;
    role: string; // 'user' | 'assistant'
    content: { message?: string; [key: string]: any };
    created_at: string;
}

export interface GetConversationHistoryResponse {
    conversation_id: string;
    messages: DialogMessage[];
    total_count: number;
}

export interface ConversationQuery {
    courseId: number;
    unitId: number;
    knowledgePointId?: number;
    attachmentId?: number;
    contentId?: number;
}

/**
 * 取得符合條件的既有對話列表（依最後更新時間新到舊排序）
 */
export async function getConversations(
    query: ConversationQuery
): Promise<GetConversationsResponse> {
    return authClient.get('/api/v1/student/chatbot/conversations', {
        course_id: query.courseId,
        unit_id: query.unitId,
        knowledge_point_id: query.knowledgePointId,
        attachment_id: query.attachmentId,
        content_id: query.contentId,
    });
}

/**
 * 取得指定對話的完整訊息紀錄
 */
export async function getConversationMessages(
    conversationId: string
): Promise<GetConversationHistoryResponse> {
    return authClient.get(
        `/api/v1/student/chatbot/conversations/${conversationId}/messages`
    );
}

// ==================== Unit Contents Types ====================

export interface UnitContentItem {
    id: number;
    title: string;
    description?: string;
    content_type: string;  // 'material', 'assignment', 'exam'
    content_subtype?: string;  // 'preview', 'review', 'exercise'
    source_type?: string;
    knowledge_point_id?: number;
    knowledge_point_name?: string;
    is_published: boolean;
    display_order?: number;
}

// ==================== Unit Knowledge Points Types ====================

export interface KnowledgePointItem {
    id: number;
    name: string;
    display_order?: number;
    preview_content?: string;  // 預習教材內容（markdown 格式）
}

// ==================== Student Unit Contents Types ====================

export interface StudentContentItem {
    id: number;
    title: string;
    content_type: string;  // 'material', 'assignment', 'exam'
    content_subtype?: string;  // 'preview', 'review', etc.
    source_type?: string;
    content?: Record<string, any> | string;  // 實際內容 (JSON or String)
    knowledge_points: Array<{ id: number; name: string }>;
    created_at: string;
    display_order?: number;
    show_answers_after?: string;
    duration_minutes?: number;
    is_preview_completed?: boolean;
    is_submitted?: boolean;
    include_in_grade?: boolean;
    assignment_type?: string;  // 'questions' or 'file_upload'
    description?: string | null; // Assignment description (Markdown)
    end_time?: string | null;  // 繳交截止時間 (ISO format)
    is_expired?: boolean; // 是否已過期
    has_practice_questions?: boolean; // 是否有對應的練習題目
    is_visible?: boolean; // 是否對學生顯示
}

export interface StudentUnitContentsResponse {
    unit_id: number;
    unit_name: string;
    items: StudentContentItem[];
}

// ==================== Previous Submission Types ====================

export interface PreviousSubmission {
    submission_id: number;
    content_id: number;
    score?: number;
    percentage?: number;
    submitted_at?: string;
    time_spent_minutes?: number;
    can_retry: boolean;
    show_answers: boolean;
    include_in_grade: boolean;
    is_manual: boolean;
    results: QuestionResult[];
}

/**
 * 取得單元的所有教材、作業和測驗（新版 API）
 */
export async function getStudentUnitContents(
    unitId: number
): Promise<StudentUnitContentsResponse> {
    return authClient.get(`/api/student/units/${unitId}/contents`);
}

export interface ReadingLogRequest {
    unit_session_id?: string;
    content_id: number;
    unit_id: number;
    stay_duration_seconds: number;
    max_scroll_depth: number;
    citation_interactions?: any[];
    exit_action?: string; // 'next_item', 'back_to_course'
}

/**
 * 記錄學生閱讀教材細節
 */
export async function submitReadingLog(
    data: ReadingLogRequest
): Promise<any> {
    return authClient.post(`/api/student/reading/logs`, data);
}

/**
 * 記錄學生閱讀教材細節 (保證發送，適用於組件卸載/視窗關閉)
 */
export async function submitReadingLogKeepalive(
    data: ReadingLogRequest
): Promise<any> {
    const token = localStorage.getItem('access_token');
    return fetch(`${API_BASE_URL}/api/student/reading/logs`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` })
        },
        body: JSON.stringify(data),
        keepalive: true
    }).catch(err => console.error('[Log] Keepalive fetch failed:', err));
}

// ==================== Preview APIs ====================

/**
 * 取得預習教材內容
 */
export async function getPreviewContent(
    kpId: number
): Promise<PreviewContentResponse> {
    return authClient.get(`/api/student/kps/${kpId}/preview-content`);
}

/**
 * 取得練習題目
 */
export async function getQuestions(
    kpId: number,
    options?: {
        count?: number;
        exclude_answered?: boolean;
    }
): Promise<QuestionsResponse> {
    const params = new URLSearchParams();
    if (options?.count) params.append('count', options.count.toString());
    if (options?.exclude_answered !== undefined) {
        params.append('exclude_answered', options.exclude_answered.toString());
    }

    return authClient.get(`/api/student/kps/${kpId}/questions?${params.toString()}`);
}

/**
 * 取得推薦練習題目（根據多個知識點）
 */
export async function getRecommendedQuestions(
    kpIds: number[],
    courseId?: number | string,
    options?: {
        question_type?: string;
        count_per_kp?: number;
        total_max?: number;
    }
): Promise<RecommendedQuestionsResponse> {
    const params = new URLSearchParams();
    params.append('kp_ids', kpIds.join(','));
    if (courseId) params.append('course_id', courseId.toString());
    if (options?.question_type) params.append('question_type', options.question_type);
    if (options?.count_per_kp) params.append('count_per_kp', options.count_per_kp.toString());
    if (options?.total_max) params.append('total_max', options.total_max.toString());

    return authClient.get(`/api/student/recommended-questions?${params.toString()}`);
}
/**
 * 取得知識點抽取的題目作答記錄
 */
export async function getKPQuestionLogs(
    kpIds: number[],
    stage: 'preview' | 'review' = 'preview'
): Promise<{ logs: any[] }> {
    return authClient.get(`/api/student/kps/logs?kp_ids=${kpIds.join(',')}&stage=${stage}`);
}


/**
 * 記錄學生作答
 */
export async function submitQuestionLog(
    data: QuestionLogRequest
): Promise<QuestionLogResponse> {
    return authClient.post(`/api/student/question-logs`, data);
}

/**
 * 批次評估答案
 */
export async function batchEvaluate(
    logIds: number[]
): Promise<BatchEvaluateResponse> {
    return authClient.post(`/api/student/question-logs/batch-evaluate`, { log_ids: logIds });
}

/**
 * 開始學習 Session
 */
export async function startLearningSession(data: {
    course_id: number;
    unit_id: number;
    context_data?: any;
}): Promise<{ session_id: string }> {
    return authClient.post(`/api/student/sessions/start`, data);
}

export async function sendSessionHeartbeat(sessionId: string): Promise<any> {
    return authClient.post(`/api/student/sessions/${sessionId}/heartbeat`);
}

/**
 * 提交作業
 */
export async function submitAssignment(
    contentId: number,
    data: SubmissionRequest
): Promise<SubmissionResponse> {
    return authClient.post(`/api/student/assignments/${contentId}/submit`, data);
}

/**
 * 提交考試
 */
export async function submitExam(
    contentId: number,
    data: SubmissionRequest
): Promise<SubmissionResponse> {
    return authClient.post(`/api/student/exams/${contentId}/submit`, data);
}

/**
 * 取得歷史提交記錄
 */
export async function getSubmission(
    contentId: number
): Promise<PreviousSubmission | null> {
    try {
        return await authClient.get(`/api/student/submissions/${contentId}`);
    } catch (err: any) {
        // 404 = 未提交過
        if (err?.response?.status === 404 || err?.status === 404) {
            return null;
        }
        throw err;
    }
}

/**
 * 評估知識點精熟度 (BERT + LIME)
 */
export async function evaluateMastery(
    kpId: number,
    data: MasteryEvaluateRequest
): Promise<MasteryEvaluateResponse> {
    return authClient.post(`/api/student/mastery/kps/${kpId}/evaluate`, data);
}

/**
 * 取得 LIME 報告的完整 URL
 */
export function getLimeReportUrl(reportPath: string): string {
    return `${API_BASE_URL}/${reportPath}`;
}

// ==================== Chatbot APIs ====================

/**
 * 發送訊息給 AI Chatbot
 */
export async function sendMessage(
    data: SendMessageRequest
): Promise<SendMessageResponse> {
    return authClient.post('/api/v1/student/chatbot/messages', data);
}

// ==================== LIME Report Types ====================

export interface FeatureWeight {
    keyword: string;
    weight: number;
}

export interface TextHighlight {
    start: number;
    end: number;
    keyword: string;
    weight: number;
}

export interface HighlightedText {
    original: string;
    highlights: TextHighlight[];
}

export interface LimeReportResponse {
    knowledge_point_id: number;
    knowledge_point_name: string;
    stage: string;
    feature_weights: FeatureWeight[];
    highlighted_text?: HighlightedText;
    generated_at: string;
}

export interface LimeSummary {
    top_keywords: string[];
    lime_report_url: string;
}

// ==================== Export All ====================

/**
 * Dashboard data types
 */
export interface StudentAnswerDashboard {
    question_id: number;
    answer: string;
    answered_at: string; // ISO datetime
}

export interface KnowledgePointStatusDashboard {
    knowledge_point_id: number;
    name: string;
    mastery_level: string;
    recent_answers: StudentAnswerDashboard[];
    lime_summary?: LimeSummary;
}

export interface DashboardResponse {
    course_id: number;
    unit_id: number;
    knowledge_points: KnowledgePointStatusDashboard[];
    ai_review: string;
    listening_highlights: string[];
}

/**
 * 取得儀表板資料
 */
export async function getStudentDashboard(
    courseId: number,
    unitId: number,
    options?: {
        stage?: 'preview' | 'review';
        teacherOverrideStudentId?: number;
    }
): Promise<DashboardResponse> {
    const params = new URLSearchParams({
        course_id: courseId.toString(),
        unit_id: unitId.toString(),
        stage: options?.stage || 'preview'
    });
    if (options?.teacherOverrideStudentId) {
        params.append('student_id', options.teacherOverrideStudentId.toString());
    }

    return authClient.get(`/api/v1/student/dashboard/?${params.toString()}`);
}

/**
 * 取得 LIME JSON 報告
 */
export async function getLimeReport(
    kpId: number,
    options?: {
        stage?: 'preview' | 'review';
        teacherOverrideStudentId?: number;
    }
): Promise<LimeReportResponse> {
    const stage = options?.stage || 'preview';
    const params = new URLSearchParams({ stage });
    if (options?.teacherOverrideStudentId) {
        params.append('student_id', options.teacherOverrideStudentId.toString());
    }
    // Using the dashboard endpoint as it provides highlighted_text and better caching
    return authClient.get(`/api/v1/student/dashboard/kps/${kpId}/lime-report?${params.toString()}`);
}

export interface Unit {
    id: number;
    name: string;
    topic_id?: number;
}

/**
 * 取得課程單元列表
 */
export async function getCourseUnits(courseId: number): Promise<Unit[]> {
    return authClient.get(`/api/v1/student/dashboard/courses/${courseId}/units`);
}

/**
 * 取得教材下載連結
 * 注意：此 URL 僅生成連結，實際下載可能需要 Token
 */
export function getMaterialDownloadUrl(contentId: number): string {
    return `${API_BASE_URL}/api/student/materials/${contentId}/download`;
}

export interface AnnouncementAttachment {
    id: number;
    original_file_name: string;
    file_type: string;
    file_size_bytes: number;
    uploaded_at: string;
    download_url: string;
}

export interface Announcement {
    id: number;
    title: string;
    content: string;
    is_pinned: boolean;
    is_visible: boolean;
    created_at: string;
    updated_at?: string;
    author_name: string;
    course_name?: string;
    course_id?: number;
    attachments: AnnouncementAttachment[];
}

/**
 * 取得課程公告 (特定課程)
 */
export async function getCourseAnnouncements(courseId: number): Promise<Announcement[]> {
    return authClient.get(`/api/v1/student/courses/${courseId}/announcements`);
}

/**
 * 取得所有相關公告 (跨課程)
 */
export async function getAllStudentAnnouncements(): Promise<Announcement[]> {
    return authClient.get(`/api/v1/student/announcements`);
}

/**
 * 取得學生已選修的課程
 */
// 加入課程
export async function joinCourse(enrollmentCode: string): Promise<any> {
    // ✅ Phase 4: 使用 authClient，student_id 從 JWT 自動提取
    return authClient.post('/api/v1/student/courses/join', {
        enrollment_code: enrollmentCode
    });
}

/**
 * 取得學生選修課程列表
 */
export async function getEnrolledCourses(): Promise<any[]> {
    // ✅ Phase 4: 使用 authClient，student_id 從 JWT 自動提取，無需作為參數
    return authClient.get('/api/v1/student/courses');
}


// ==================== Review Types ====================

export interface ReviewSection {
    title: string;
    content: string;
}

export interface ReviewSummary {
    title: string;
    description?: string;
    sections: ReviewSection[];
}

export interface ReviewQuizItem {
    question_id: number;
    kp_id: number;
    type: string;
    text: string;
    options?: any;
    source: string;
}

// ==================== Feature 2: Personal Review Materials ====================

export interface PersonalMaterialQuestion {
    question_id: number;
    question_text: string;
    question_type: string;
    source: 'retry' | 'random';
}

export interface PersonalMaterialKP {
    kp_id: number;
    kp_name: string;
    mastery_level: string;
    questions: PersonalMaterialQuestion[];
}

export interface PersonalMaterialsResponse {
    unit_id: number;
    kp_materials: PersonalMaterialKP[];
}

// ==================== Feature 3: Mastered KP AI Questions ====================

export interface MasteredChallengeQuestion {
    question_id: number;
    kp_id: number;
    kp_name: string;
    question_text: string;
    question_type: string;
    difficulty_level?: string;
    options?: Record<string, string> | string[];
    source: 'challenge';
}

export interface MasteredKpQuestionsResponse {
    unit_id: number;
    mastered_kp_questions: MasteredChallengeQuestion[];
    total_count: number;
}

export const studentApi = {
    // Preview
    getPreviewContent,
    getQuestions,
    submitQuestionLog,
    batchEvaluate,
    submitAssignment,
    submitExam,
    getSubmission,
    evaluateMastery,
    getLimeReportUrl,
    submitReadingLog,
    submitReadingLogKeepalive,
    startLearningSession,
    sendSessionHeartbeat,

    // Chatbot
    sendMessage,
    getConversations,
    getConversationMessages,
    
    // Dashboard & LIME
    getStudentDashboard,
    getLimeReport: async (
        kpId: number,
        options?: {
            stage?: 'preview' | 'review';
            teacherOverrideStudentId?: number;
        }
    ): Promise<LimeReportResponse> => {
        const stage = options?.stage || 'preview';
        const params = new URLSearchParams({ stage });
        if (options?.teacherOverrideStudentId) {
            params.append('student_id', options.teacherOverrideStudentId.toString());
        }
        return authClient.get(`/api/student/mastery/kps/${kpId}/explain?${params.toString()}`);
    },
    getCourseUnits,
    getCourseAnnouncements,
    getEnrolledCourses,
    getAllStudentAnnouncements,

    // Feature 2: 個人化複習教材（所有非精熟 KP 的重練題目）
    getReviewPersonalMaterials: async (
        unitId: number,
        options?: { countPerKp?: number }
    ): Promise<PersonalMaterialsResponse> => {
        const params = new URLSearchParams();
        if (options?.countPerKp) params.append('count_per_kp', options.countPerKp.toString());
        return authClient.get(`/api/student/review/units/${unitId}/personal-materials?${params.toString()}`);
    },

    // Feature 3: 精熟 KP AI 推薦挑戰題
    getReviewMasteredKpQuestions: async (
        unitId: number,
        options?: { countPerKp?: number }
    ): Promise<MasteredKpQuestionsResponse> => {
        const params = new URLSearchParams();
        if (options?.countPerKp) params.append('count_per_kp', options.countPerKp.toString());
        return authClient.get(`/api/student/review/units/${unitId}/mastered-kp-questions?${params.toString()}`);
    },

    // Materials
    getMaterialDownloadUrl: (contentId: number) => {
        return `${API_BASE_URL}/api/student/materials/${contentId}/download`;
    },

    // ==================== Challenge Logs (精熟挑戰題) ====================
    // 純 INSERT 模式：LLM 評估後才 INSERT，不觸發 BERT/LIME

    submitChallenges: async (data: SubmitChallengesRequest): Promise<SubmitChallengesResponse> => {
        return authClient.post(`/api/student/review/challenge-logs/submit`, data);
    },

    getChallengeHistory: async (questionIds: number[]): Promise<Record<string, ChallengeHistoryItem>> => {
        return authClient.post(`/api/student/review/challenge-logs/history`, { question_ids: questionIds });
    },
};

// ==================== Material Rating Types ====================

export interface MaterialRatingRequest {
    rating: number;  // 1-5
    feedback?: string;
    dimensions?: Record<string, any>;
}

export interface MaterialRatingResponse {
    id: number;
    user_id: number;
    course_id: number;
    content_id: number;
    rating: {
        score: number;
        feedback?: string;
        dimensions?: Record<string, any>;
    };
    created_at: string;
    updated_at: string;
}

export interface RatingStatsResponse {
    total_count: number;
    suggest_detailed: boolean;
}

/**
 * 提交或更新教材評分
 */
export async function submitMaterialRating(
    contentId: number,
    data: MaterialRatingRequest
): Promise<MaterialRatingResponse> {
    return authClient.post(`/api/student/materials/${contentId}/rate`, data);
}

/**
 * 取得學生對教材的評分
 */
export async function getMaterialRating(
    contentId: number
): Promise<MaterialRatingResponse | null> {
    return authClient.get(`/api/student/materials/${contentId}/rating`);
}

/**
 * 取得學生評分統計
 */
export async function getMaterialRatingStats(): Promise<RatingStatsResponse> {
    return authClient.get(`/api/student/stats/rating_count`);
}

/**
 * 批次提交教材評分
 */
export async function batchSubmitMaterialRating(
    contentIds: number[],
    data: MaterialRatingRequest
): Promise<{ status: string; count: number }> {
    return authClient.post(`/api/student/materials/batch-rate`, {
        content_ids: contentIds,
        ...data
    });
}

// ==================== Attachment Viewer API ====================

/**
 * 取得附件內容（用於線上瀏覽）
 */
export async function getAttachmentView(attachmentId: number): Promise<AttachmentViewResponse> {
    return authClient.get(`/api/attachments/${attachmentId}/view`);
}

/**
 * 取得附件檔案 Blob (用於 PDF 顯示，需帶相關 Auth Header)
 */
export async function getAttachmentBlob(attachmentId: number): Promise<Blob> {
    return authClient.get(`/api/attachments/${attachmentId}/view`, undefined, {
        responseType: 'blob'
    });
}

/**
 * 記錄附件閱讀時間
 */
export async function logAttachmentReadingTime(
    attachmentId: number,
    readingTimeSeconds: number
): Promise<{ message: string }> {
    return authClient.post(`/api/attachments/${attachmentId}/reading-time`, {
        reading_time_seconds: readingTimeSeconds
    });
}
// ==================== File Submission APIs ====================

export interface SubmissionFile {
    name: string;
    original_name: string;
    path: string;
    size: number;
    type: string;
    uploaded_at: string;
}

export interface FileSubmissionStatus {
    id: number;
    content_id: number;
    user_id: number;
    files: SubmissionFile[];
    score: number | null;
    feedback: string | null;
    is_manual: boolean;
    submitted_at: string;
    updated_at: string | null;
}

/**
 * 上傳檔案作業 (學生端)
 */
export async function uploadFileSubmission(
    contentId: number,
    file: File
): Promise<FileSubmissionStatus> {
    const formData = new FormData();
    formData.append('file', file);

    const token = localStorage.getItem('access_token');
    const response = await fetch(`${API_BASE_URL}/api/student/file-submissions/${contentId}/upload`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`
        },
        body: formData
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: '上傳失敗' }));
        throw new Error(error.detail || '上傳失敗');
    }

    return response.json();
}

/**
 * 取得檔案作業繳交狀態 (學生端)
 */
export async function getFileSubmissionStatus(
    contentId: number
): Promise<FileSubmissionStatus | null> {
    try {
        return await authClient.get(`/api/student/file-submissions/${contentId}`);
    } catch (err: any) {
        if (err?.response?.status === 404 || err?.status === 404) {
            return null;
        }
        throw err;
    }
}

/**
 * 刪除已繳交的單一檔案
 */
export async function deleteFileSubmissionFile(
    contentId: number,
    filename: string
): Promise<FileSubmissionStatus> {
    const token = localStorage.getItem('access_token');
    const response = await fetch(`${API_BASE_URL}/api/student/file-submissions/${contentId}/files/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: '刪除失敗' }));
        throw new Error(error.detail || '刪除失敗');
    }

    return response.json();
}

export default studentApi;
