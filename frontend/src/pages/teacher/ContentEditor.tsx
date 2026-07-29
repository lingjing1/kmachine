import React, { useState, useEffect, useRef, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import API_BASE_URL from '../../config/api';
import { useParams, useNavigate, useLocation, useOutletContext } from 'react-router-dom';
import { useUser } from '../../contexts/UserContext';
import { FaSpinner, FaTimesCircle, FaSave, FaCalculator, FaRobot, FaDatabase, FaPlus, FaCheckCircle, FaCalendarAlt } from 'react-icons/fa';
import Button from '../../components/common/Button';
import Toast from '../../components/common/Toast';
import { ContentRenderer, ContentRendererRef } from '../../components/common/ContentRenderer';
import { GradingEditor } from '../../components/teacher/GradingEditor';
import Footer from '../../components/common/Footer';
import RightPanelTabs from '../../components/common/RightPanelTabs';
import CriticResultPanel from '../../components/teacher/CriticResultPanel';
import EvaluationPromptPanel from '../../components/teacher/EvaluationPromptPanel';
import Modal from '../../components/common/Modal';
import { ReferenceDrawer } from '../../components/teacher/ReferenceDrawer';
import QuestionMetadataDrawer, { QuestionMetadataData, QuestionMetadataDrawerRef } from '../../components/teacher/QuestionMetadataDrawer';
import TeacherRatingModal from '../../components/teacher/TeacherRatingModal';
import TeacherKPQuestionsView from '../../components/teacher/TeacherKPQuestionsView';

import {
    triggerCriticEvaluation,
    fetchCriticEvaluations,
    EvaluationResponse,
    QuestionCriticState
} from '../../services/criticApi';
import { distributePoints, parseQuestionsFromContent, GradingConfig } from '../../utils/grading';
import QuestionBankPanel, { QuestionBankItem, QuestionBankPanelRef } from '../../components/teacher/QuestionBankPanel';
import PublishSettingsPanel, { PublishingSettings } from '../../components/teacher/PublishSettingsPanel';
import { IoRefreshCircle } from "react-icons/io5";
// import { ImCancelCircle } from "react-icons/im"; // Removed as unused
import { FaFileCirclePlus, FaFilePen, FaFileCircleCheck, FaArrowLeft } from "react-icons/fa6";
import Tooltip from '../../components/common/Tooltip';
import ConfirmDialog from '../../components/common/ConfirmDialog';
import authClient from '../../services/authClient';
import FileSubmissionsPanel from '../../components/teacher/FileSubmissionsPanel';
import RichTextEditor from '../../components/common/RichTextEditor';
import { ActiveTimer } from '../../utils/activeTimer';

interface OutletContext {
    setBreadcrumbPaths: (paths: Array<{ name: string; path: string }>) => void;
    setHeaderActions?: (actions: React.ReactNode) => void;
}

interface GenerationResult {
    job_id: number;
    status: 'pending' | 'running' | 'completed' | 'failed';
    content?: {
        id: number;
        title: string;
        content_type: string;
        content: any; // The actual content
        display_type?: string;
    };
    error?: string;
    created_at: string;
    source_ids?: number[];
    generated_source_ids?: number[];
    selected_kp_ids?: number[];
    selected_kp_names?: string[];
    current_agent?: string;
    current_step_desc?: string;
    current_avatar?: string;
    prompt?: string;
    material_type?: string;
    length?: string;
    question_types?: string[];
    question_count?: number;
    total_iterations?: number;
}



export default function ContentEditor() {
    const { courseId, jobId, contentId } = useParams<{ courseId: string; jobId: string; contentId: string }>();
    const isEditing = !!contentId;
    const navigate = useNavigate();
    const location = useLocation();
    const { user } = useUser();
    const { setHeaderActions } = useOutletContext<OutletContext>();

    const searchParams = new URLSearchParams(location.search);
    const urlType = searchParams.get('type') as 'material' | 'exam' | null;
    const urlUnitId = searchParams.get('unit_id') ? parseInt(searchParams.get('unit_id')!) : null;
    const mode = searchParams.get('mode') as 'edit' | 'add' | 'manual' | null; // 'edit' = editing existing, 'add' = adding from history, 'manual' = manual creation
    const isManualMode = mode === 'manual'; // Manual question creation mode
    const isNewMode = !jobId && !contentId;

    const [result, setResult] = useState<GenerationResult | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'error' | 'info' }>({
        show: false, message: '', type: 'success'
    });
    const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);

    // Mirror refs to avoid stale closures in fire-and-forget effects
    const selectedChunkRef = useRef<any>(null);
    const selectedQuestionIdRef = useRef<number | null>(null);
    const resultRef = useRef<GenerationResult | null>(null);
    // Tracks whether the reference click came from an exam question or a summary section
    const [refSourceType, setRefSourceType] = useState<'question' | 'section' | null>(null);
    const refSourceTypeRef = useRef<'question' | 'section' | null>(null);

    // Teacher Rating State
    const [showRatingModal, setShowRatingModal] = useState(false);
    const [ratingContentId, setRatingContentId] = useState<number | null>(null);
    const [isRegenerationRating, setIsRegenerationRating] = useState(false);

    // Duplicate Question Modal State
    const [isDuplicateModalOpen, setIsDuplicateModalOpen] = useState(false);
    const [pendingDuplicateQuestion, setPendingDuplicateQuestion] = useState<QuestionBankItem | null>(null);
    const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

    // [New] KP Lookup Modal State
    const [lookupKPName, setLookupKPName] = useState('');
    const [lookupKPId, setLookupKPId] = useState<number | undefined>(undefined);
    const [lookupKPCount, setLookupKPCount] = useState<number>(0);
    const [isKPLookupModalOpen, setIsKPLookupModalOpen] = useState(false);
    const isNavigatingRef = useRef(false);
    const [isTitleFocused, setIsTitleFocused] = useState(false);

    useEffect(() => {
        console.log('[ContentEditor] COMPONENT MOUNTED', { jobId, contentId });
        return () => {
            // Mark as navigating if we haven't already, to prevent double unmount logs
            // But we let the cleanup function handle the automatic log if no action was logged
        };
    }, [jobId, contentId]);

    // Logging State for Experiment Tracking (Active Time Only)
    const editorTimer = useMemo(() => new ActiveTimer(), []);
    const actionLoggedRef = useRef<boolean>(false);
    const latestResultRef = useRef<GenerationResult | null>(null);


    // Track latest result
    useEffect(() => {
        latestResultRef.current = result;
    }, [result]);

    // Start Timer on Mount
    useEffect(() => {
        editorTimer.start();
        return () => {
            editorTimer.stop();
        };
    }, [editorTimer]);

    const sessionIdFromState = (location.state as any)?.sessionId;
    console.log('[ContentEditor] sessionIdFromState:', sessionIdFromState);

    const getActiveDurationSeconds = () => {
        return Math.floor(editorTimer.getElapsedSeconds());
    };

    // [LOGGING] Increment view count once when content finishes loading in edit mode.
    // Fires after `result` is populated (not on bare mount) to ensure the JWT token
    // and content data are both available, preventing a silent 401 failure.
    const viewLoggedRef = useRef<boolean>(false);
    useEffect(() => {
        if (isEditing && contentId && courseId && mode !== 'add' && result && !viewLoggedRef.current) {
            viewLoggedRef.current = true;
            authClient.post(`/api/courses/${courseId}/contents/${contentId}/view`).catch(err => {
                console.error('Failed to increment content view count:', err);
                viewLoggedRef.current = false; // allow retry on next render if request failed
            });
        }
    }, [isEditing, contentId, courseId, mode, result]);

    // Reusable helper to extract generated content ID for logging
    const getGeneratedContentId = (res: GenerationResult | null) => {
        console.log('[ContentEditor] Detecting ID from result:', res);
        if (!res?.content) return null;
        const content = res.content as any;

        // 1. If it's a course_content object (editing existing), we want source_id (the original generated_content_id)
        if (content.source_type === 'generated_content' && content.source_id) {
            return Number(content.source_id);
        }

        // 2. If it's a direct generated_content object (new generation)
        if (content.id) {
            return Number(content.id);
        }

        return null;
    };

    // Handle abrupt exit / Discard via Navigation/Close
    useEffect(() => {
        const logDiscard = () => {
            // If already logged OR successfully navigated via UI buttons, skip
            if (actionLoggedRef.current || isNavigatingRef.current) return;

            const currentResult = latestResultRef.current;
            const generatedContentId = getGeneratedContentId(currentResult);

            console.log('[ContentEditor] logDiscard (unmount/unload) triggered', {
                hasResult: !!currentResult,
                generatedContentId,
                isManualMode
            });

            // If we have a generated ID, log the discard
            if (generatedContentId && !isManualMode) {
                actionLoggedRef.current = true;
                const durationSeconds = getActiveDurationSeconds();
                const payload = JSON.stringify({
                    generated_content_id: generatedContentId,
                    action_type: 'discard',
                    edit_duration_seconds: durationSeconds,
                    content_snapshot: currentResult?.content?.content
                });

                const token = sessionStorage.getItem('access_token') || '';
                try {
                    fetch(`${API_BASE_URL}/api/teacher/logs/action`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${token}`
                        },
                        body: payload,
                        keepalive: true
                    });
                } catch (e) {
                    console.error('Failed to send discard log via fetch', e);
                }
            }
            // SPECIAL CASE: User closed tab while generation was in progress (jobId exists but result.content doesn't)
            else if (jobId && !isManualMode && !currentResult?.content) {
                // We can't easily get the generated_content_id here because it's not finished
                // We'll let the backend or future logic handle "abandoned" jobs
            }
        };

        window.addEventListener('beforeunload', logDiscard);
        return () => {
            logDiscard(); // Final attempt on component unmount
            window.removeEventListener('beforeunload', logDiscard);
        };
    }, [jobId, isManualMode]);

    // Header Actions (Cancel Button)
    useEffect(() => {
        if (setHeaderActions) {
            setHeaderActions(
                <Tooltip content="返回課程頁面" position="bottom">
                    <button
                        onClick={() => setShowDiscardConfirm(true)}
                        className="
                                flex items-center gap-2 text-neutral-text-secondary font-medium
                                transition-all duration-200 hover:text-blue-700 group
                            "
                    >
                        <div className="w-10 h-10 rounded-xl bg-white border border-gray-200 shadow-sm flex items-center justify-center transition-all duration-200 group-hover:bg-blue-50 group-hover:border-blue-200">
                            <FaArrowLeft className="w-4 h-4 flex-shrink-0 group-hover:scale-110 transition-transform" />
                        </div>
                        <span className="max-lg:hidden whitespace-nowrap">返回課程</span>
                    </button>
                </Tooltip>
            );
        }
        return () => {
            if (setHeaderActions) setHeaderActions(null);
        };
    }, [setHeaderActions]);

    const handleDiscardConfirm = async () => {
        setShowDiscardConfirm(false);
        isNavigatingRef.current = true; // Prevents the useEffect cleanup from logging again

        const currentResult = result;
        const generatedContentId = getGeneratedContentId(currentResult);

        console.log('[ContentEditor] handleDiscardConfirm triggered', {
            hasResult: !!currentResult,
            generatedContentId,
            isManualMode,
            actionLogged: actionLoggedRef.current
        });

        if (!isManualMode && !actionLoggedRef.current) {
            actionLoggedRef.current = true;
            const durationSeconds = getActiveDurationSeconds();

            try {
                // CASE 1: Generation finished -> Log with ID
                if (generatedContentId) {
                    const payload = {
                        generated_content_id: generatedContentId,
                        action_type: 'discard',
                        edit_duration_seconds: durationSeconds,
                        content_snapshot: currentResult?.content?.content
                    };
                    await authClient.post('/api/teacher/logs/action', payload);
                }
                // CASE 2: Generation NOT finished -> Log abort (Backend needs job_id or we track it differently)
                else if (jobId) {
                    console.log('[ContentEditor] Discarding unfinished job:', jobId);
                    // Currently our /logs/action requires generated_content_id. 
                    // We can't log to that specific table yet.
                }
            } catch (err) {
                console.error('Failed to log discard action:', err);
            }
        }

        navigate(`/teacher/courses/${courseId}`);
    };

    // Target Type State (Initialize from URL, then independent)
    const initialType = (urlType === 'material') ? 'material' : 'exam';
    const [targetType, setTargetType] = useState<'material' | 'exam'>(initialType);
    // Target Unit State (Persist from URL)
    const [targetUnitId] = useState<number | null>(urlUnitId);

    // Course Name State
    const [courseName, setCourseName] = useState('');

    // Metadata for Question Bank
    const [units, setUnits] = useState<any[]>([]);
    const [knowledgePoints, setKnowledgePoints] = useState<{
        id: number | string;
        name: string;
        mermaid_id?: string;
        category?: string;
        source_name?: string;
        source_type?: string;
    }[]>([]);

    const [publishingSettings, setPublishingSettings] = useState<PublishingSettings>({
        is_visible: true,
        allow_review: true,
        content_subtype: searchParams.get('subtype') || 'homework' // Initialize from url subtype if available
    });
    const [weight, setWeight] = useState<number>(0);

    const memoizedAvailableKPs = useMemo(() => {
        const selectedIds = (result?.selected_kp_ids || []).map(id => String(id));
        const selectedNames = result?.selected_kp_names || [];

        // 1. Start with all discovered knowledgePoints
        const allMapped = knowledgePoints.map(kp => ({
            id: String(kp.id),
            name: kp.name,
            mermaid_id: kp.mermaid_id,
            category: kp.category || 'extracted',
            source_name: kp.source_name,
            source_type: kp.source_type
        }));

        // 2. Add any selected KPs that aren't already in the list
        // (e.g. from the recent generation result that might not be in the metadata fetch yet)
        selectedIds.forEach((id, index) => {
            if (id && id !== 'null' && id !== 'undefined' && !allMapped.some(kp => kp.id === id)) {
                allMapped.push({
                    id: id,
                    name: selectedNames[index] || `KP ${id}`,
                    mermaid_id: id.startsWith('doc_') ? undefined : id,
                    category: 'extracted',
                    source_name: undefined,
                    source_type: undefined
                });
            }
        });

        // Deduplicate by ID
        const seenIds = new Set();
        return allMapped.filter(kp => {
            if (seenIds.has(kp.id)) return false;
            seenIds.add(kp.id);
            return true;
        });
    }, [knowledgePoints, result?.selected_kp_ids, result?.selected_kp_names]);

    // Refs
    const questionBankRef = useRef<QuestionBankPanelRef>(null);
    const rendererRef = useRef<ContentRendererRef>(null);

    /**
     * 點擊知識點放大鏡：開啟彈窗查看題庫中的題目
     */
    const handleKPLookup = (kpName: string, kpId?: number) => {
        setLookupKPName(kpName);
        setLookupKPId(kpId);
        setLookupKPCount(0); // Reset count
        setIsKPLookupModalOpen(true);
    };

    useEffect(() => {
        if (!courseId) return;
        const fetchMetadata = async () => {
            // Fetch Course Details (Name)
            try {
                const courseRes = await fetch(`${API_BASE_URL}/api/courses/${courseId}`);
                if (courseRes.ok) {
                    const data = await courseRes.json();
                    setCourseName(data.name || '');
                }
            } catch (e) {
                console.error("Failed to fetch course details", e);
            }

            // Fetch Units
            try {
                const unitsRes = await fetch(`${API_BASE_URL}/api/courses/${courseId}/units`);
                if (unitsRes.ok) setUnits(await unitsRes.json());
            } catch (e) {
                console.error("Failed to fetch units", e);
            }

            // Fetch Knowledge Points
            try {
                // Determine source context from result content
                let uniqueContentIds: number[] = [];

                // Check top-level source_ids from result (new structured format)
                if (result?.source_ids && Array.isArray(result.source_ids)) {
                    uniqueContentIds = result.source_ids;
                }
                // Fallback to result.content.source_ids (legacy/compatibility)
                else if (result?.content) {
                    const contentAny = result.content as any;
                    if (contentAny.source_ids && Array.isArray(contentAny.source_ids)) {
                        uniqueContentIds = contentAny.source_ids;
                    } else if (contentAny.source_id && contentAny.source_id > 0) {
                        uniqueContentIds = [contentAny.source_id];
                    }
                }

                // [NEW] Always use the unified group retrieval if unit_id is available
                // This ensures "Unit KPs" are always shown even for new generations
                const currentUnitId = targetUnitId || (result as any)?.unit_id || urlUnitId;

                const params = new URLSearchParams();
                let url;

                if (currentUnitId) {
                    params.append('unit_id', currentUnitId.toString());
                    url = `${API_BASE_URL}/api/courses/${courseId}/knowledge-points?${params.toString()}`;
                } else if (uniqueContentIds.length > 0) {
                    uniqueContentIds.forEach(id => params.append('unique_content_ids', id.toString()));
                    url = `${API_BASE_URL}/api/courses/${courseId}/content-knowledge-points?${params.toString()}`;
                } else {
                    url = `${API_BASE_URL}/api/courses/${courseId}/knowledge-points?${params.toString()}`;
                }

                const kpsRes = await fetch(url);
                if (kpsRes.ok) setKnowledgePoints(await kpsRes.json());
            } catch (e) {
                console.error("Failed to fetch knowledge points", e);
            }
        };
        fetchMetadata();
    }, [courseId, jobId, contentId]);


    // Helper to flatten content structure (shared logic)
    const flattenContent = (data: any) => {
        if (!data.content || !data.content.content) return data;

        if (!data.content.retrieved_text_chunks) {
            const nested = data.content.content?.retrieved_text_chunks || data.content.content?.content?.retrieved_text_chunks;
            if (nested) data.content.retrieved_text_chunks = nested;
        }

        // [FIX] Unwrap accidentally double-wrapped content (legacy fix)
        // Only unwrap if the outer object does NOT have a 'type' (meaning it's just a wrapper)
        if (data.content && data.content.content && data.content.content.content &&
            !data.content.content.type &&
            (data.content.content.content.sections || Array.isArray(data.content.content.content))) {
            // If the inner content looks like the real data (has sections or is array), lift it up
            data.content.content = data.content.content.content;
        }

        // [FIX] Infer type for unwrapped summary content
        if (data.content.content && data.content.content.sections && !data.content.content.type) {
            data.content.content.type = 'summary_report';
            data.content.content.material_type = 'preview'; // Default or based on logic
        }

        // [FIX] Skip flattening for Summary objects - they should remain as-is
        if (data.content.content && (data.content.content.sections || data.content.content.type === 'summary_report')) {
            return data;
        }

        let flattenedItems: any[] = [];
        let qIndex = 1;

        const processContent = (rawContent: any) => {
            let itemsToProcess: any[] = [];
            if (Array.isArray(rawContent)) {
                itemsToProcess = rawContent;
            } else if (typeof rawContent === 'object' && rawContent !== null) {
                // Check if it's a numeric-keyed object (e.g. {"0": {...}, "1": {...}})
                const keys = Object.keys(rawContent);
                // Relaxed detection: if it has key "0", we treat it as a potential array masquerading as an object
                const hasZeroIndex = keys.includes('0');

                if (hasZeroIndex) {
                    // Extract only keys that look like integers
                    const numericKeys = keys.filter(k => !isNaN(parseInt(k)) && /^\d+$/.test(k));

                    if (numericKeys.length > 0) {
                        itemsToProcess = numericKeys
                            .sort((a, b) => parseInt(a) - parseInt(b))
                            .map(k => rawContent[k]);
                    } else {
                        itemsToProcess = [rawContent];
                    }
                } else {
                    itemsToProcess = [rawContent];
                }
            }

            itemsToProcess.forEach(item => {
                // Case A: Block with questions
                if (item.questions && Array.isArray(item.questions)) {
                    const blockType = item.type || item.question_type || 'unknown';
                    item.questions.forEach((q: any) => {
                        // Priority: 1. Existing numeric q.id 2. Generate if missing or string
                        let finalId = q.id;
                        if (finalId === undefined || finalId === null || (typeof finalId === 'string' && isNaN(Number(finalId)))) {
                            const stringToHash = (typeof finalId === 'string' && finalId.startsWith('manual-'))
                                ? finalId
                                : (q.question_text || `q-${qIndex}-${Date.now()}`);
                            let hash = 0;
                            for (let i = 0; i < stringToHash.length; i++) {
                                hash = ((hash << 5) - hash) + stringToHash.charCodeAt(i);
                                hash |= 0;
                            }
                            finalId = Math.abs(hash);
                            q.id = finalId; // Write back so it persists in JSONB
                        } else if (typeof finalId === 'string' && !isNaN(Number(finalId))) {
                            finalId = Number(finalId);
                            q.id = finalId;
                        }

                        flattenedItems.push({
                            ...q,
                            id: finalId,
                            type: q.type || q.question_type || blockType,
                            question_type: q.question_type || blockType,
                            question_number: qIndex++
                        });
                    });
                    return;
                }
                // Case B: Standalone Question
                if (item.question_text) {
                    let finalId = item.id;
                    if (finalId === undefined || finalId === null || (typeof finalId === 'string' && isNaN(Number(finalId)))) {
                        let hash = 0;
                        const s = item.question_text || `sq-${qIndex}`;
                        for (let i = 0; i < s.length; i++) {
                            hash = ((hash << 5) - hash) + s.charCodeAt(i);
                            hash |= 0;
                        }
                        finalId = Math.abs(hash);
                        item.id = finalId;
                    }
                    flattenedItems.push({ ...item, id: finalId, question_number: qIndex++ });
                    return;
                }
                // Case C: Recursion
                let subContent = item.content;
                let depth = 0;
                while (typeof subContent === 'string' && depth < 3) {
                    let clean = subContent.trim();
                    if (clean.startsWith('```')) clean = clean.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
                    try { subContent = JSON.parse(clean); } catch (e) { break; }
                    depth++;
                }

                if (Array.isArray(subContent)) {
                    if (item.title && item.title !== data.content.title) {
                        flattenedItems.push({ type: 'section_header', title: item.title, content: item.description || '' });
                    }
                    processContent(subContent);
                    return;
                }
                if (typeof subContent === 'object' && subContent !== null && (subContent.questions || subContent.content)) {
                    if (item.title && item.title !== data.content.title) {
                        flattenedItems.push({ type: 'section_header', title: item.title, content: item.description || '' });
                    }
                    processContent(subContent);
                    return;
                }
                // Case D: Leaf
                if (item.title || item.content) {
                    flattenedItems.push(item);
                }
            });
        };

        processContent(data.content.content);

        if (flattenedItems.length > 0) {
            data.content.content = flattenedItems;
        }
        return data;
    };

    // [NEW] Reset evaluation state when Job ID changes to ensure fresh state for new generations
    useEffect(() => {
        if (jobId) {
            console.log(`[ContentEditor] JobId changed to ${jobId}, resetting evaluation state.`);
            setCriticEvaluation(null);
            setHasFetchedHistory(false);
            autoTriggerJobIdRef.current = null;
        }
    }, [jobId]);

    // Fetch existing content if editing
    useEffect(() => {
        if (isEditing && contentId && courseId) {
            setLoading(true);
            (async () => {
                try {
                    // [FIX] Use different endpoints based on mode
                    // 'edit' mode: uses existing course_content (linked to course/unit)
                    // 'add' mode: uses historical generated_content (not yet in unit, or from another unit)
                    const fetchUrl = mode === 'add'
                        ? `${API_BASE_URL}/api/v1/generated_materials/${contentId}`
                        : `${API_BASE_URL}/api/courses/${courseId}/contents/${contentId}`;

                    const response = await fetch(fetchUrl);
                    if (response.ok) {
                        const found = await response.json();

                        // Construct initial result object
                        let initialResult: any = {
                            job_id: found.job_id || 0,
                            status: 'completed',
                            content: {
                                id: found.id,
                                title: found.title,
                                content_type: found.content_type,
                                unit_id: found.unit_id,
                                source_type: found.source_type,
                                source_id: found.source_id,
                                // Important: Ensure retrieved_text_chunks are preserved if they exist in the nested content
                                // The backend typically stores the full generated JSON in `content` column
                                content: found.content
                            } as any,
                            created_at: found.created_at || new Date().toISOString()
                        };

                        // [NEW] If we have a job_id, fetch job metadata to restore generation parameters (prompt, KPs, etc.)
                        if (found.job_id) {
                            try {
                                const jobRes = await fetch(`${API_BASE_URL}/api/v1/jobs/${found.job_id}`);
                                if (jobRes.ok) {
                                    const jobData = await jobRes.json();
                                    initialResult = {
                                        ...initialResult,
                                        prompt: jobData.prompt,
                                        source_ids: jobData.source_ids,
                                        generated_source_ids: jobData.generated_source_ids,
                                        selected_kp_ids: jobData.selected_kp_ids,
                                        selected_kp_names: jobData.selected_kp_names,
                                        material_type: jobData.material_type,
                                        length: jobData.length,
                                        question_types: jobData.question_types,
                                        question_count: jobData.question_count,
                                        total_iterations: jobData.total_iterations,
                                    };
                                }
                            } catch (err) {
                                console.error('Failed to fetch job metadata for regeneration:', err);
                            }
                        }

                        // Apply shared flattening logic
                        const processedData = flattenContent(initialResult);

                        // [FIX] Inject default recommendation config for materials if missing
                        if (processedData.content.content_type === 'material' && !processedData.content.content.recommendation_config) {
                            if (processedData.content.content.sections || processedData.content.content.type === 'summary_report') {
                                processedData.content.content.recommendation_config = { total_max: 5, count_per_kp: 1, enabled: true };
                            }
                        }

                        setResult(processedData);

                        // [FIX] In 'add' mode, respect the intended type from URL (container type)
                        // rather than the historical content_type which might be mislabeled as 'material'
                        const normalizedType = (mode === 'add' && urlType)
                            ? urlType
                            : (found.content_type === 'assignment' ? 'exam' : found.content_type as 'material' | 'exam');

                        setTargetType(normalizedType);
                        const { is_visible, content_subtype, start_time, end_time, duration_minutes, allow_review, show_answers_after, assignment_type, description } = found;

                        // [FIX] In 'add' mode, prefer the URL subtype (e.g. 'homework' or 'preview') 
                        // over the historical guess (e.g. 'summary_report' or 'material')
                        const finalSubtype = (mode === 'add' && searchParams.get('subtype'))
                            ? searchParams.get('subtype')!
                            : content_subtype;

                        setPublishingSettings({
                            is_visible,
                            content_subtype: finalSubtype,
                            start_time, end_time, duration_minutes, allow_review, show_answers_after,
                            assignment_type: assignment_type || (normalizedType === 'exam' ? 'questions' : undefined),
                            description: description || null
                        });
                        if (typeof found.weight === 'number') setWeight(found.weight);

                        // Set grading config
                        setIncludeInGrade(found.include_in_grade);
                        if (found.question_grading) {
                            setGradingConfig({
                                grading_method: found.question_grading.grading_method || 'per_question',
                                total_points: found.total_points || 100,
                                question_types: found.question_grading.question_types || {
                                    multiple_choice: 5,
                                    short_answer: 10,
                                    true_false: 2,
                                    fill_in_blank: 4
                                },
                                individual_questions: found.question_grading.individual_questions || {}
                            });
                        }
                    } else {
                        throw new Error('Failed to fetch content');
                    }
                } catch (err) {
                    console.error("Failed to fetch content", err);
                    setToast({ show: true, message: '載入內容失敗', type: 'error' });
                } finally {
                    setLoading(false);
                }
            })();
        } else if (isNewMode) {
            // Initialize empty result for new mode (no job)
            const isMaterial = urlType === 'material';
            const defaultTitle = isMaterial ? '新教材' : '新試卷';
            const newType = isMaterial ? 'material' : 'exam';

            setResult({
                job_id: 0,
                status: 'completed',
                content: {
                    id: 0,
                    title: defaultTitle,
                    content_type: newType,
                    content: {
                        content: [],
                        title: defaultTitle
                    }
                },
                created_at: new Date().toISOString()
            } as any);

            // Set default publishing settings for new content
            if (setPublishingSettings) {
                setPublishingSettings(prev => ({
                    ...prev,
                    content_subtype: 'homework'
                }));
            }

            setLoading(false);
        }
    }, [isEditing, contentId, courseId, isNewMode, urlType]);

    // Question Bank Logic
    const handleQuestionToggle = (q: QuestionBankItem, allowDuplicate = false) => {
        if (!result || !result.content) return;

        // Deep clone
        const newContentWrapper = JSON.parse(JSON.stringify(result.content));

        let items: any[] = [];

        // Check if wrapper.content is the array directly
        if (Array.isArray(newContentWrapper.content)) {
            items = newContentWrapper.content;
        }
        // Check if wrapper.content.content is the array (standard nested structure)
        else if (newContentWrapper.content && Array.isArray(newContentWrapper.content.content)) {
            items = newContentWrapper.content.content;
        }
        // Fallback: try to find it in wrapper directly if needed (legacy)
        else if (Array.isArray(newContentWrapper.content)) {
            items = newContentWrapper.content;
        }

        // 1. Try to find by ID first (Reverse search to remove latest added duplicate)
        let existingIdx = -1;
        for (let i = items.length - 1; i >= 0; i--) {
            if (items[i].saved_question_bank_id === q.id) {
                existingIdx = i;
                break;
            }
        }

        let foundByText = false;

        // 2. If not found by ID, try to find by content similarity
        if (existingIdx === -1) {
            // Normalize function
            const normalize = (str: string) => (str || '').trim();
            const qText = normalize(q.question_data?.question_text || q.question_data?.question);
            const qTitle = normalize(q.title);

            // Reverse search here too
            for (let i = items.length - 1; i >= 0; i--) {
                const item = items[i];
                const itemText = normalize(item.question_text || item.question || item.question_data?.question_text || item.question_data?.question);
                const itemTitle = normalize(item.title);

                // Strict match
                if (itemTitle === qTitle && itemText === qText) {
                    existingIdx = i;
                    foundByText = true;
                    break;
                }
            }
        }

        if (existingIdx >= 0) {
            if (foundByText && !items[existingIdx].saved_question_bank_id) {
                // Found by text, check duplicate permission
                // Note: This path is usually handled by checkDuplicateAndToggle before calling this
                if (!allowDuplicate) {
                    // Should act as no-op or return, but technically we shouldn't get here if checkDuplicateAndToggle did its job
                    return;
                }
            } else {
                // Remove (Toggle Off)
                items.splice(existingIdx, 1);

                // Update result
                setResult((prev: any) => {
                    const newResult = { ...prev, content: newContentWrapper };

                    // Auto-recalculate grading if enabled
                    if (includeInGrade) {
                        const parsed = parseQuestionsFromContent(newContentWrapper);
                        if (parsed.questions.length > 0) {
                            const totalPoints = gradingConfig.total_points || 100;
                            const { questions, types } = distributePoints(parsed.questions, totalPoints);
                            // const hasRemainder = totalPoints % parsed.questions.length !== 0;
                            // User requested to maintain current grading method regardless of remainder

                            setGradingConfig(prevConfig => ({
                                ...prevConfig,
                                grading_method: prevConfig.grading_method,
                                question_types: types,
                                individual_questions: questions
                            }));
                        }
                    }
                    return newResult;
                });
                return;
            }
        }

        // Add (New or Duplicate Confirmed)
        const newItem = {
            ...q.question_data,
            saved_question_bank_id: q.id,
            title: q.title,
            type: q.question_type,
            question_type: q.question_type,
            question_number: items.length + 1
        };
        items.push(newItem);

        // Update result
        setResult((prev: any) => {
            const newResult = { ...prev, content: newContentWrapper };

            // Auto-recalculate grading if enabled
            if (includeInGrade) {
                const parsed = parseQuestionsFromContent(newContentWrapper);
                if (parsed.questions.length > 0) {
                    const totalPoints = gradingConfig.total_points || 100;
                    const { questions, types } = distributePoints(parsed.questions, totalPoints);


                    // const hasRemainder = totalPoints % parsed.questions.length !== 0;

                    setGradingConfig(prevConfig => ({
                        ...prevConfig,
                        grading_method: prevConfig.grading_method,
                        question_types: types,
                        individual_questions: questions
                    }));
                }
            }
            return newResult;
        });

        // Scroll to the new item
        setFocusIndex(items.length - 1); // Index of the new item
    };

    // Derived selected question IDs
    const selectedQuestionIds = (() => {
        if (!result?.content) return [];
        const ids: number[] = [];

        const traverse = (items: any[]) => {
            if (!Array.isArray(items)) return;
            items.forEach(item => {
                if (item.saved_question_bank_id) ids.push(item.saved_question_bank_id);
                if (item.questions) traverse(item.questions);
                if (item.content && Array.isArray(item.content)) traverse(item.content);
            });
        };

        // Try to find the list
        const contentRoot = (result.content as any).content;
        if (contentRoot && Array.isArray(contentRoot.content)) {
            traverse(contentRoot.content);
        } else if (Array.isArray(contentRoot)) {
            traverse(contentRoot);
        }

        return ids;
    })();

    // Grading State
    const [gradingConfig, setGradingConfig] = useState<GradingConfig>({
        total_points: 100,
        grading_method: 'by_question_type',
        question_types: [],
        individual_questions: []
    });
    const [isGradingValid, setIsGradingValid] = useState(true);
    // Default includeInGrade to false for new exams (Homework default), unless specified in URL or loaded from DB later
    const [includeInGrade, setIncludeInGrade] = useState(() => {
        const param = searchParams.get('grade');
        if (param !== null) return param !== 'false';
        return false;
    });

    // Helper to recalculate grading
    const recalculateGrading = (currentContent: any) => {
        const parsed = parseQuestionsFromContent(currentContent);
        // Only recalculate if we have questions
        if (parsed.questions.length > 0) {
            const totalPoints = gradingConfig.total_points || 100;
            const { questions, types } = distributePoints(parsed.questions, totalPoints);
            // const hasRemainder = totalPoints % parsed.questions.length !== 0;

            setGradingConfig(prev => ({
                ...prev,
                grading_method: prev.grading_method,
                question_types: types,
                individual_questions: questions
            }));
        }
    };

    // Auto-enable grading when switching to Quiz/Midterm/Final
    useEffect(() => {
        if (targetType === 'exam' && publishingSettings?.content_subtype) {
            const subtype = publishingSettings.content_subtype;
            const isGradedType = ['quiz', 'midterm', 'final'].includes(subtype);

            if (isGradedType) {
                if (!includeInGrade) {
                    setIncludeInGrade(true);
                    // Will trigger checking logic via the includeInGrade effect below or we can call explicitly
                    // But we need the latest content. verification:
                    if (result?.content) {
                        recalculateGrading(result.content);
                    }
                }
            } else if (subtype === 'homework') {
                // Optional: Disable grading if switched back to homework?
                // User requirement implies "Default new to Homework (Grading Disabled)". 
                // It doesn't explicitly say "Switching to Homework should DISABLE grading".
                // But it "Verify scores do NOT appear/update" implies disabled.
                // Let's safe-guard: if user manually enabled grading for homework, we might keep it?
                // But the requirement says "Switching to Quiz... Enable".
                // It doesn't say "Switching to Homework will automatically Disable".
                // However, verification step 4 says: "Switch Type back to Homework (Grading OFF)".
                // I will NOT auto-disable for now to avoid data loss, unless strictly required. 
                // Wait, logic says "Grading is disabled by default".
                // If I switch to Homework, I probably shouldn't force disable if they want to grade a homework.
                // But generally homeworks aren't graded in this context?
                // I will leave it as manual disable or keep as is.
            }
        }
    }, [publishingSettings?.content_subtype, targetType]);

    useEffect(() => {
        if (includeInGrade && result?.content) {
            // Always recalculate/reset distribution when enabled to ensure consistency
            recalculateGrading(result.content);
        }
    }, [includeInGrade]);

    // Critic State
    const [criticEvaluation, setCriticEvaluation] = useState<EvaluationResponse | null>(null);
    const [hasFetchedHistory, setHasFetchedHistory] = useState(false);
    const [isEvaluating, setIsEvaluating] = useState(false);
    const [showReEvalModal, setShowReEvalModal] = useState(false);
    const [showRefineConfirm, setShowRefineConfirm] = useState(false);
    const [questionCritics, setQuestionCritics] = useState<QuestionCriticState[]>([]);
    const [activeRightTab, setActiveRightTab] = useState<'grading' | 'critic' | 'bank' | 'manual' | 'publish'>('critic'); // Default to critic
    const [contentVersion, setContentVersion] = useState(0);
    const [focusIndex, setFocusIndex] = useState<number | null>(null);
    const [autoEditIndex, setAutoEditIndex] = useState<number | null>(null); // Auto-trigger edit mode for new questions


    const checkDuplicateAndToggle = (q: QuestionBankItem, forceToggle = false) => {
        console.log('🔍 checkDuplicateAndToggle TRIGGERED', { title: q.title, id: q.id, forceToggle });

        if (!result || !result.content) {
            console.log('❌ No result or content found');
            return;
        }

        const contentWrapper = result.content;
        let items: any[] = [];
        // Helper to extract items (simplified from toggle logic)
        if (Array.isArray(contentWrapper.content)) {
            items = contentWrapper.content;
        } else if (contentWrapper.content && Array.isArray(contentWrapper.content.content)) {
            items = contentWrapper.content.content;
        } else if (Array.isArray(contentWrapper)) {
            // Handle edge case if result.content IS the array? Unlikely given interface
            items = contentWrapper as any;
        }

        // Logic to detect if we have a duplicate
        // User requested to use question_text as the main title and for duplicate detection
        // const normalize = (str: string) => (str || '').trim(); // Removed toLowerCase to respect case in question text for now, or should I keep it? Safest to keep it for check.
        const normalizeCase = (str: string) => (str || '').trim().toLowerCase();

        const qText = normalizeCase(q.question_data?.question_text || q.question_data?.question || q.title);
        // We no longer strictly compare the DB 'title' field as per request, but we can still use it as a fallback
        // const qTitle = normalizeCase(q.title); 

        console.log('🔎 Checking duplication for Text:', { qTextLength: qText.length, sample: qText.substring(0, 30) });
        // console.log('📋 Current Canvas Items:', items.map(i => ({
        //     id: i.saved_question_bank_id,
        //     title: normalize(i.title || i.question_data?.title),  // Also log the normalized title we will compare against
        //     textLength: normalize(i.question_text || i.question || i.question_data?.question_text || i.question_data?.question).length
        // })));

        const existingIdIdx = items.findIndex((item: any) => item.saved_question_bank_id === q.id);

        if (existingIdIdx !== -1) {
            if (!forceToggle) {
                // Already linked -> Scroll to it
                console.log('✅ Question already linked (has ID), scrolling to it');
                // Reset focus index first to ensure effect triggers even if index is same
                setFocusIndex(null);
                setTimeout(() => {
                    setFocusIndex(existingIdIdx);
                }, 10);
                return;
            } else {
                // Force toggle -> Remove it
                console.log('✅ Force toggle on linked question -> Removing');
                handleQuestionToggle(q);
                return;
            }
        }

        const duplicateIdx = items.findIndex((item: any) => {
            const itemText = normalizeCase(item.question_text || item.question || item.question_data?.question_text || item.question_data?.question);
            // Also check item title just in case it holds the text (which is common for manual questions)
            const itemTitle = normalizeCase(item.title);

            // Primary check: Question Text matches
            if (itemText && itemText === qText) {
                console.log('⚡ MATCH FOUND: Question Text Match');
                return true;
            }

            // Secondary check: Title matches Question Text (if title was used as text holder)
            // Or if explicit title exists and matches (less prioritized but valid if text is missing)
            if (itemTitle && itemTitle === qText) {
                console.log('⚡ MATCH FOUND: Item Title matches Question Text');
                return true;
            }

            return false;
        });

        console.log('🏁 Search Result:', { existingIdIdx, duplicateIdx });

        if (duplicateIdx !== -1) {
            // Duplicate found and NOT linked -> Ask confirmation
            setPendingDuplicateQuestion(q);
            setIsDuplicateModalOpen(true);
        } else {
            // No duplicate, clean add
            handleQuestionToggle(q);
        }
    };

    const confirmAddDuplicate = () => {
        if (pendingDuplicateQuestion) {
            handleQuestionToggle(pendingDuplicateQuestion, true); // true = allowDuplicate
            setIsDuplicateModalOpen(false);
            setPendingDuplicateQuestion(null);
        }
    };

    // Auto-switch tab based on mode
    useEffect(() => {
        if (isEditing) {
            setActiveRightTab('publish');
        } else if (isManualMode) {
            setActiveRightTab('publish');
        } else if (!jobId) {
            // New Mode (Creating new exam)
            setActiveRightTab('publish');
        }
    }, [jobId, isManualMode, targetType, isEditing]);

    // ... Reference Modal State ...
    const [showReferenceModal, setShowReferenceModal] = useState(false);
    const [selectedChunk, setSelectedChunk] = useState<any | null>(null);
    const [selectedEvidence, setSelectedEvidence] = useState("");
    const [selectedMatchScore, setSelectedMatchScore] = useState<number | undefined>(undefined);

    // Auto-fetch evaluation data when job_id is available (for edit mode)
    useEffect(() => {
        if (result?.job_id && result.job_id > 0 && !criticEvaluation) {
            // Fetch latest evaluation for this job
            (async () => {
                try {
                    const evaluation = await fetchCriticEvaluations(result.job_id);
                    if (evaluation) {
                        setCriticEvaluation(evaluation);

                        // Parse question-level critics if available
                        if (evaluation.evaluation?.quality_critic?.evaluations) {
                            const critics: QuestionCriticState[] = evaluation.evaluation.quality_critic.evaluations
                                .map((rubricEval: any, index: number) => {
                                    let severity: 'high' | 'medium' | 'low' = 'low';
                                    if (rubricEval.rating < 3) severity = 'high';
                                    else if (rubricEval.rating < 4) severity = 'medium';

                                    return {
                                        questionId: index + 1,
                                        hasFeedback: rubricEval.rating < 4,
                                        feedbackSummary: rubricEval.feedback,
                                        severity: severity,
                                    };
                                });
                            setQuestionCritics(critics);
                        }
                    }
                } catch (error) {
                    console.error('Failed to fetch evaluation:', error);
                } finally {
                    setHasFetchedHistory(true);
                }
            })();
        } else if (result?.job_id && criticEvaluation) {
            setHasFetchedHistory(true);
        }
    }, [result?.job_id, criticEvaluation]);

    // Set breadcrumb paths
    useEffect(() => {
        // Breadcrumbs are handled by Teacher parent layout based on path
    }, [courseId, targetType, isEditing, mode, courseName]);

    // Polling Logic
    useEffect(() => {
        let isMounted = true;
        const poll = async () => {
            if (!jobId) return;
            try {
                const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}`);
                if (response.ok) {
                    const data = await response.json();
                    if (isMounted) {
                        // Apply shared flattening logic
                        const processedData = flattenContent(data);

                        // [FIX] Inject default recommendation config for new generations
                        if (data.status === 'completed' && processedData.content &&
                            (processedData.content.sections || processedData.content.type === 'summary_report')) {
                            if (!processedData.content.recommendation_config) {
                                processedData.content.recommendation_config = { total_max: 5, count_per_kp: 1, enabled: true };
                            }
                        }

                        setResult(processedData);

                        if (data.status === 'completed' || data.status === 'failed') {
                            setLoading(false);
                            return true; // Stop polling
                        }



                    }
                }
            } catch (error) {
                console.error("Polling error", error);
            }
            return false;
        };

        const runPolling = async () => {
            await poll(); // Initial fetch
            const interval = setInterval(async () => {
                const finished = await poll();
                if (finished) clearInterval(interval);
            }, 2000);
            return () => clearInterval(interval);
        };

        runPolling();

        return () => { isMounted = false; };
    }, [jobId]);

    // Calculate content stats when result changes


    // Critic Evaluation Handlers
    const handleTriggerEvaluation = async (workflow: 2 | 3 | 4 = 4) => {
        const targetJobId = jobId ? parseInt(jobId) : (result?.job_id || 0);

        if (!targetJobId || !result) {
            setToast({ show: true, message: '無法識別生成任務 ID，僅能評估剛生成的內容', type: 'error' });
            return;
        }

        setIsEvaluating(true);
        setToast({
            show: true,
            message: '開始評估...',
            type: 'info'
        });
        
        try {
            const evaluation = await triggerCriticEvaluation(
                targetJobId,
                workflow, // dynamic workflow
                'quick'
            );

            setCriticEvaluation(evaluation);

            // Parse question-level critics if available
            if (evaluation.evaluation.quality_critic?.evaluations) {
                const critics: QuestionCriticState[] = evaluation.evaluation.quality_critic.evaluations
                    .map((rubricEval, index) => {
                        let severity: 'high' | 'medium' | 'low' = 'low';
                        if (rubricEval.rating < 3) severity = 'high';
                        else if (rubricEval.rating < 4) severity = 'medium';

                        return {
                            questionId: index + 1,
                            hasFeedback: rubricEval.rating < 4,
                            feedbackSummary: rubricEval.feedback,
                            severity: severity,
                        };
                    })
                    .filter(c => c.hasFeedback);

                setQuestionCritics(critics);
            }

            // Switch to critic tab if we have results
            if (targetType === 'exam' && evaluation) {
                setActiveRightTab('critic');
            }

            setToast({
                show: true,
                message: '評估完成！',
                type: 'success'
            });
        } catch (error) {
            console.error('Evaluation failed:', error);
            setToast({
                show: true,
                message: '評估失敗，請稍後再試',
                type: 'error'
            });
        } finally {
            setIsEvaluating(false);
        }
    };

    // [NEW] Auto-trigger Evaluation after Generation
    const autoTriggerJobIdRef = useRef<string | null>(null);
    useEffect(() => {
        // Only auto-trigger if:
        // 1. We have a jobId (Fresh generation)
        // 2. Generation is completed (loading is false and status is completed)
        // 3. We haven't already auto-triggered for THIS jobId
        // 4. No evaluation exists yet and we aren't currently evaluating
        if (jobId && !loading && result?.status === 'completed' &&
            !isEvaluating && hasFetchedHistory && !criticEvaluation && autoTriggerJobIdRef.current !== jobId) {

            console.log(`[ContentEditor] Auto-triggering evaluation for jobId: ${jobId}`);
            autoTriggerJobIdRef.current = jobId;
            handleTriggerEvaluation(4); // Default to Full Evaluation
        }
    }, [jobId, contentId, loading, result?.status, isEvaluating, criticEvaluation, hasFetchedHistory]);




    const handleRefine = () => {
        console.log('[ContentEditor] handleRefine triggered. Result:', result);
        const generatedContentId = getGeneratedContentId(result);
        console.log('[ContentEditor] Detected generatedContentId:', generatedContentId);

        if (generatedContentId) {
            setRatingContentId(generatedContentId);
            setIsRegenerationRating(true);
            setShowRatingModal(true);
        } else {
            console.warn('[ContentEditor] No generated content ID found for rating, falling back to basic confirm.');
            setShowRefineConfirm(true);
        }
    };

    const confirmRefine = async () => {
        setShowRefineConfirm(false);
        if (!result) return;

        // Reconstruct auto-prompt logic to strip it from result.prompt
        const getCleanPrompt = (rawPrompt: string, res: GenerationResult) => {
            if (!rawPrompt) return '';

            const targetType = res.content?.content_type || res.material_type ? 'material' : 'exam'; // Heuristic
            const isExam = targetType === 'exam' || (res.question_types && res.question_types.length > 0) || res.question_count;

            let autoPart = '';
            if (isExam) {
                const typesStr = (res.question_types || []).length > 0 ? (res.question_types || []).join('、') : '混合題型';
                autoPart = `根據以下教材內容，生成一份包含 ${res.question_count || 5} 題的測驗。`;
                if ((res.question_types || []).length > 0) {
                    autoPart += `題型包含：${typesStr}。`;
                }
            } else {
                let detailDesc = '';
                switch (res.length) {
                    case 'concise': detailDesc = '精簡的重點摘要，列點式呈現核心概念'; break;
                    case 'detailed': detailDesc = '詳盡的內容解析，包含核心概念解釋、關鍵定義與實際應用範例'; break;
                    case 'standard': default: detailDesc = '標準的重點整理，歸納出核心概念與關鍵術語'; break;
                }
                autoPart = `請針對教材內容進行${detailDesc}。`;
            }

            // Stripping logic
            let cleaned = rawPrompt;
            // The prompt might contain the autoPart multiple times if previously regenerated multiple times improperly
            // We use a loop to strip all occurrences from the start
            while (autoPart && cleaned.startsWith(autoPart)) {
                cleaned = cleaned.substring(autoPart.length).trim();
            }
            return cleaned;
        };

        // Construct reconstruction state for GeneratorSettings
        // Reconstruct selectedKPDetails (using current knowledgePoints if possible for details)
        const selectedKPDetails = (result.selected_kp_ids || []).map((id, index) => {
            const kpId = Number(id);
            const found = knowledgePoints.find(kp => Number(kp.id) === kpId);
            return {
                id: kpId,
                name: found?.name || (result.selected_kp_names || [])[index] || `KP ${id}`,
                mermaid_id: found?.mermaid_id
            };
        });

        console.log('[ContentEditor] Regenerate - result object:', result);
        console.log('[ContentEditor] Regenerate - result prompt:', result.prompt);

        // Reconstruct selectedSourceKeys
        const sourceKeys = new Set<string>();
        (result.source_ids || []).forEach(id => sourceKeys.add(`uploaded:${id}`));
        (result.generated_source_ids || []).forEach(id => {
            if (id) sourceKeys.add(`generated:${id}`);
        });

        // Params to pass back
        const paramsToPass = {
            prompt: getCleanPrompt(result.prompt || '', result),
            materialType: result.material_type || 'preview',
            summaryDetail: result.length || 'standard',
            questionTypes: result.question_types || [],
            questionCount: result.question_count || 5,
            maxIterations: result.total_iterations || 3
        };

        console.log('[ContentEditor] Navigating back to GeneratorSettings with params:', paramsToPass);

        // [NEW] Log the regenerate action to the backend
        const generatedContentId = getGeneratedContentId(result);

        if (generatedContentId && !actionLoggedRef.current) {
            try {
                actionLoggedRef.current = true;
                const durationSeconds = getActiveDurationSeconds();
                const payload = {
                    generated_content_id: generatedContentId,
                    action_type: 'regenerate',
                    edit_duration_seconds: durationSeconds,
                    content_snapshot: result.content?.content
                };
                console.log('[ContentEditor] Logging regenerate action to backend...', payload);
                await authClient.post('/api/teacher/logs/action', payload);
            } catch (err) {
                console.error('Failed to log regenerate action:', err);
            }
        }

        navigate(`/teacher/courses/${courseId}/generate?type=${targetType}&unit_id=${targetUnitId}`, {
            state: {
                reconstruct: true,
                selectedSourceKeys: Array.from(sourceKeys),
                selectedKPDetails,
                params: paramsToPass,
                sessionId: sessionIdFromState // Carry forward the session ID
            }
        });
    };


    const handleSave = async () => {
        if (targetType === 'exam' && !isGradingValid) {
            setToast({ show: true, message: '請修正配分設定（總分需相符）', type: 'error' });
            return;
        }

        setSaving(true);
        try {
            if (!result?.content) throw new Error("No content to save");

            // Determine if this is a create or update operation
            // - If mode=add, always create new (even if contentId exists)
            // - If mode=edit or no mode, update existing
            const isUpdate = isEditing && mode === 'edit';
            const isAddFromHistory = mode === 'add';

            const endpoint = isUpdate
                ? `/api/courses/${courseId}/contents/${contentId}`
                : `/api/courses/${courseId}/contents`;

            // Extract selected KPs from location state (passed from GeneratorSettings)
            const selectedKPs = (location.state as any)?.selectedKPs || [];
            const selectedKpNames = selectedKPs.map((kp: any) => kp.name);

            // [FIX] Prepare content for save
            // Summary logic: If it's a summary (has sections), we want { sections: ..., type: ..., chunks: ... }
            // Exam logic: We want { content: [questions], chunks: ... }
            let contentBody = result.content.content;

            // [FIX] Check for pending edits in Renderer
            // If user typed but didn't click individual save, we capture it here
            if (rendererRef.current) {
                const pending = rendererRef.current.getPendingContent();
                if (pending) {
                    // Use pending content as the latest source of truth
                    // Pending content is the full content object (e.g. { content: [...] })
                    // We need to resolve what "contentBody" expects.
                    // contentBody usually expects the JSON object.
                    contentBody = pending;

                    // Also update state so UI usage reflects it if save fails or continues
                    // But we can't update state synchronously inside event handler effectively for this scope
                }
            }

            // [VALIDATION] Check if all questions have text and answers
            if (targetType === 'exam') {
                let questionsToValidate = [];
                if (Array.isArray(contentBody)) {
                    questionsToValidate = contentBody;
                } else if (contentBody && Array.isArray(contentBody.content)) {
                    questionsToValidate = contentBody.content;
                }

                for (let i = 0; i < questionsToValidate.length; i++) {
                    const q = questionsToValidate[i];
                    const type = q.type || q.question_type;

                    // Skip section headers or instruction blocks
                    if (type === 'section_header' || (!q.question_text && q.title && !q.options)) continue;

                    // 1. Check Question Text
                    if (!q.question_text?.trim()) {
                        setToast({ show: true, message: `第 ${i + 1} 題題目內容尚未填寫`, type: 'error' });
                        setSaving(false);
                        return;
                    }

                    // 2. Check Answers/Options based on type
                    if (type === 'multiple_choice') {
                        // Check if options exist and are not empty
                        if (!q.options || Object.keys(q.options).length === 0) {
                            setToast({ show: true, message: `第 ${i + 1} 題尚未設定選項`, type: 'error' });
                            setSaving(false);
                            return;
                        }

                        // Check if all option values are filled
                        const allOptionsFilled = Object.values(q.options).every((opt: any) => opt && String(opt).trim().length > 0);
                        if (!allOptionsFilled) {
                            setToast({ show: true, message: `第 ${i + 1} 題有選項內容尚未填寫`, type: 'error' });
                            setSaving(false);
                            return;
                        }

                        // Check if correct answer is selected
                        if (!q.correct_answer) {
                            setToast({ show: true, message: `第 ${i + 1} 題尚未設定正確答案`, type: 'error' });
                            setSaving(false);
                            return;
                        }
                    } else if (type === 'true_false') {
                        // Correct answer for T/F (usually 'true' or 'false')
                        if (q.correct_answer === undefined || q.correct_answer === null || q.correct_answer === '') {
                            setToast({ show: true, message: `第 ${i + 1} 題尚未設定正確答案`, type: 'error' });
                            setSaving(false);
                            return;
                        }
                    } else if (type === 'short_answer') {
                        // [RELAXED] Short answer sample answer is now optional
                        // No logic needed here for now
                    } else if (type === 'fill_in_blank' || type === 'fill_in_the_blank') {
                        // [STRICT] Fill-in-blank MUST have correct_answer
                        if (!q.correct_answer?.trim()) {
                            setToast({ show: true, message: `第 ${i + 1} 題填空題尚未填寫正確答案`, type: 'error' });
                            setSaving(false);
                            return;
                        }

                        // [UI CHECK] Check if question text contains underscores for blanks
                        if (!q.question_text?.includes('____')) {
                            setToast({ show: true, message: `第 ${i + 1} 題填空題題目中尚未包含空格 (請使用至少四個底線 ____)`, type: 'info' });
                            // We allow saving with warning for now, or we can choose to return. 
                            // User request said "挖____的空格", let's make it a warning.
                        }
                    }
                }
            }

            // 1. Determine structure and inject type if needed
            // CRITICAL: Flatten structure - if it's an array of questions, save it directly.
            let finalContent;

            if (contentBody && (contentBody.type === 'summary' || contentBody.type === 'summary_report') && contentBody.sections) {
                // Backend already provides complete summary structure, use as-is
                finalContent = contentBody;
            } else if (contentBody && contentBody.sections) {
                // Legacy format: wrap sections
                finalContent = {
                    ...contentBody,
                    sections: contentBody.sections,
                    type: contentBody.type || 'summary_report',
                    subtype: contentBody.subtype || 'preview'
                };
            } else if (Array.isArray(contentBody)) {
                // ✅ FLAT: Save question array directly without wrapping in { content: ... }
                finalContent = contentBody;
            } else if (contentBody && contentBody.content && Array.isArray(contentBody.content)) {
                // ✅ FLAT: Unwrap existing wrap if detected
                // BUT keep other metadata if it's not JUST a wrap (like recommendation_config)
                if (contentBody.recommendation_config || contentBody.type) {
                    finalContent = { ...contentBody };
                } else {
                    finalContent = contentBody.content;
                }
            } else {
                finalContent = contentBody;
            }

            // [Validation] Check weight if grading is enabled
            if (targetType === 'exam' && includeInGrade) {
                if (weight <= 0) {
                    setToast({ show: true, message: '開啟配分時，學期成績權重必須大於 0%', type: 'error' });
                    setSaving(false);
                    return;
                }
            }



            // Extract content_subtype from finalContent (for material type: preview/review)
            // ✅ FIX: Due to nested structure, subtype might be in finalContent.content.subtype
            let contentSubtype: string | null = null;
            if (targetType === 'material') {
                // Try multiple levels to handle nested structure, fallback to URL parameter
                contentSubtype = finalContent?.subtype || finalContent?.content?.subtype || searchParams.get('subtype') || null;
            }

            // Construct payload matching ContentCreate schema
            const payload: any = {
                title: result.content.title,
                // If user selected a subtype in PublishingSettings, use it. Default to 'homework' if coming from assignment flow.
                content_type: targetType === 'exam' ? 'exam' : 'material', // MUST be strictly 'material' or 'exam'
                content_subtype: isAddFromHistory
                    ? searchParams.get('subtype') || contentSubtype || targetType // Fallback to targetType if it accidentally holds the subtype
                    : (targetType === 'exam'
                        ? (publishingSettings.content_subtype || searchParams.get('subtype') || 'homework')
                        : contentSubtype),

                source_type: isUpdate
                    ? ((result.content as any).source_type || 'generated_content')
                    : (isManualMode ? 'manual' : 'generated_content'),
                source_id: (result.content as any).source_type === 'generated_content'
                    ? (result.content as any).source_id || 0
                    : (isAddFromHistory ? parseInt(contentId!) : result.content.id),

                // [FIX] unit_id: Prefer URL param > content unit > default 1
                // targetUnitId is state initialized once, might be stale. urlUnitId is fresh from location.
                unit_id: urlUnitId ?? targetUnitId ?? (result.content as any).unit_id ?? (isUpdate ? undefined : 1),

                // [NEW] Multi-source tracking
                source_ids: result.source_ids || (result.content as any)?.source_ids || [],

                selected_kp_names: selectedKpNames, // ✅ Pass selected KP names for Promotion & Linking
                selected_kps: selectedKPs.map((kp: any) => ({ name: kp.name, level: kp.level })), // ✅ Pass structured KPs with level

                content: finalContent,

                // Grading & specific fields
                include_in_grade: (targetType === 'exam') && includeInGrade,
                total_points: ((targetType === 'exam') && includeInGrade) ? gradingConfig.total_points : 100,
                question_grading: ((targetType === 'exam') && includeInGrade) ? {
                    grading_method: gradingConfig.grading_method,
                    question_types: gradingConfig.question_types,
                    individual_questions: gradingConfig.individual_questions
                } : null,
                weight: ((targetType === 'exam') && includeInGrade) ? weight : 0,

                // Defaults
                is_published: false,
                is_visible: publishingSettings.is_visible,
                start_time: publishingSettings.start_time,
                end_time: publishingSettings.end_time,
                duration_minutes: publishingSettings.duration_minutes,
                allow_review: publishingSettings.allow_review,
                show_answers_after: publishingSettings.show_answers_after,
                assignment_type: publishingSettings.assignment_type || 'questions',
                description: publishingSettings.description || null,

                author_id: user?.user_id, // ✅ Pass author_id from frontend

                // [NEW] Experiment Logging: Edit Duration (Active Time Only)
                edit_duration_seconds: getActiveDurationSeconds()
            };

            // Prevent double logging to discard on navigation
            actionLoggedRef.current = true;

            if (isUpdate) {
                await authClient.put(endpoint, payload);
            } else {
                await authClient.post(endpoint, payload);
            }

            setToast({
                show: true,
                message: isUpdate ? '更新成功' : '儲存成功',
                type: 'success'
            });

            // Navigate back to course page after save
            // Add refresh flag to force re-fetch of course data
            const finishSaving = () => {
                setTimeout(() => {
                    navigate(`/teacher/courses/${courseId}`, {
                        state: { refresh: true },
                        replace: false
                    });
                }, 1000);
            };

            // Trigger Rating Modal only if it's new content from AI generation (has jobId)
            if (!isUpdate && !isManualMode && jobId && result.content.id) {
                setRatingContentId(result.content.id);
                setShowRatingModal(true);
                // We don't call finishSaving yet, modal handles it via onClose or onSubmitSuccess
            } else {
                finishSaving();
            }

            // If saving material, also ingest
            // Sync to uploaded_contents if it is a material and comes from generation (so it appears in context list)
            // If saving material, also ingest
            // Sync to uploaded_contents if it is a material and comes from generation (so it appears in context list)
            // Note: ingest_course_content API (backend) now handles this automatically on save/update
        } catch (error: any) {
            console.error(error);
            setToast({ show: true, message: `儲存失敗: ${error.message}`, type: 'error' });
        } finally {
            setSaving(false);
        }
    };
    // Question Bank Drawer State
    const [bankDrawer, setBankDrawer] = useState<{
        isOpen: boolean;
        isCollapsed: boolean;
        questionIndex: number | null;
        question: any | null;
        bankData?: any;  // 完整的題庫資料（用於編輯模式）
    }>({
        isOpen: false,
        isCollapsed: false,
        questionIndex: null,
        question: null
    });

    // Ref to access drawer methods (submit)
    const drawerRef = useRef<QuestionMetadataDrawerRef>(null);
    // Ref to store the very latest question content during save
    const latestQuestionRef = useRef<any>(null);

    // Question Bank Handlers
    const handleAddToBank = (idx: number, question: any) => {
        // ✅ Prioritize pending data from the card (if in edit mode)
        let latestQuestion = question;
        if (rendererRef.current) {
            const pending = rendererRef.current.getPendingContent();
            if (pending) {
                // Determine the correct path to the question within the pending object
                const pContent = pending.content || pending;
                const items = Array.isArray(pContent) ? pContent : (pContent.content || pContent.questions || []);
                if (Array.isArray(items) && items[idx]) {
                    latestQuestion = items[idx];
                }
            }
        }

        let resolvedKpId = latestQuestion.kp_id;

        // Helper to normalize strings for comparison (remove spaces, punctuation, lowercase)
        const normalize = (s: string) => (s || '').toString().trim()
            .replace(/[\s\-_（）\(\)\[\]【】]/g, '')
            .replace(/[.,!?;:，。！？；：]/g, '')
            .toLowerCase();

        if (!resolvedKpId && question.related_kps && Array.isArray(question.related_kps) && question.related_kps.length > 0) {
            const firstKpName = question.related_kps[0];
            const normalizedTarget = normalize(firstKpName);

            // 1. Try exact normalized match among all fetched KPs (context-specific)
            let match = knowledgePoints.find(kp => normalize(kp.name) === normalizedTarget);

            // 2. Try partial match among all fetched KPs
            if (!match) {
                match = knowledgePoints.find(kp => {
                    const normalizedKP = normalize(kp.name);
                    return normalizedKP.includes(normalizedTarget) || normalizedTarget.includes(normalizedKP);
                });
            }

            // 3. If no match in state, check against selected KPs for this job explicitly
            if (!match && result?.selected_kp_ids && result.selected_kp_names) {
                const nameIdx = result.selected_kp_names.findIndex(name => normalize(name) === normalizedTarget);
                if (nameIdx !== -1) {
                    resolvedKpId = result.selected_kp_ids[nameIdx];
                } else {
                    // Try partial match in selected names
                    const partialIdx = result.selected_kp_names.findIndex(name => {
                        const normalizedKP = normalize(name);
                        return normalizedKP.includes(normalizedTarget) || normalizedTarget.includes(normalizedKP);
                    });
                    if (partialIdx !== -1) {
                        resolvedKpId = result.selected_kp_ids[partialIdx];
                    }
                }
            }

            if (match) {
                resolvedKpId = match.id;
            }
        }

        // 4. Ultimate Fallback: If still not resolved and there's only one selected KP, use it as default
        if (!resolvedKpId && result?.selected_kp_ids && result.selected_kp_ids.length === 1) {
            resolvedKpId = result.selected_kp_ids[0];
        }

        if (!resolvedKpId) {
            // Automatically enter edit mode on the card to let user select KP
            if (rendererRef.current) {
                rendererRef.current.startEditing(idx);
            }
        }

        setBankDrawer({
            isOpen: true,
            isCollapsed: false,
            questionIndex: idx,
            question: { ...latestQuestion, kp_id: resolvedKpId }
        });
        // Exclusive: Close reference drawer
        setShowReferenceModal(false);
    };

    const handleConfirmAddToBank = async (data: QuestionMetadataData) => {
        if (!bankDrawer.question || bankDrawer.questionIndex === null || !result?.content) return;

        // Ensure unit_id is available
        const unitId = targetUnitId || urlUnitId;
        if (!unitId) {
            setToast({ show: true, message: '無法取得單元 ID，請重新整理頁面', type: 'error' });
            return;
        }

        // Check if we updating an existing bank question
        const isUpdate = !!bankDrawer.bankData?.id;

        // Validation: Ensure kp_id exists (check drawer data OR pending card edit)
        let finalKpId = data.kp_id || bankDrawer.question?.kp_id;
        let finalQuestionData = bankDrawer.question;

        if (rendererRef.current) {
            const pending = rendererRef.current.getPendingContent();
            if (pending) {
                // Determine the correct path to the question within the pending object
                const pContent = pending.content || pending;
                const items = Array.isArray(pContent) ? pContent : (pContent.content || pContent.questions || []);
                if (Array.isArray(items) && items[bankDrawer.questionIndex!]) {
                    const latest = items[bankDrawer.questionIndex!];
                    finalQuestionData = latest;
                    if (latest.kp_id) finalKpId = latest.kp_id;
                }
            }
        }

        if (!finalKpId) {
            setToast({ show: true, message: '請先在題目上選擇一個知識點才能加入題庫', type: 'error' });
            return;
        }

        // Use the latest question content: prioritize finalQuestionData (from pending card edit) 
        // over latestQuestionRef.current (from saved edit) over initial drawer question
        const questionPayload = finalQuestionData || latestQuestionRef.current || bankDrawer.question;

        // Normalize question type (migration from fill_in_the_blank -> fill_in_blank)
        let qType = questionPayload.type || questionPayload.question_type || 'short_answer';
        if (qType === 'fill_in_the_blank') qType = 'fill_in_blank';

        try {
            const endpoint = isUpdate
                ? `/api/courses/${courseId}/question-bank/${bankDrawer.bankData.id}`
                : `/api/courses/${courseId}/question-bank`;

            const savedItem = await (isUpdate
                ? authClient.put<any>(endpoint, {
                    title: data.title,
                    description: data.description,
                    question_data: { ...questionPayload, type: qType, question_type: qType },
                    question_type: qType,
                    difficulty_level: data.difficulty_level ? {
                        1: 'easy',
                        2: 'medium',
                        3: 'hard',
                        4: 'hard'
                    }[data.difficulty_level] : null,
                    estimated_time_minutes: data.estimated_time_minutes,
                    tags: (questionPayload.is_manual || String(questionPayload.id || '').startsWith('manual-')) ? ['手動新增'] : [],
                    unit_id: data.unit_id === undefined ? unitId : data.unit_id,
                    kp_id: finalKpId
                })
                : authClient.post<any>(endpoint, {
                    title: data.title,
                    description: data.description,
                    question_data: { ...questionPayload, type: qType, question_type: qType },
                    question_type: qType,
                    difficulty_level: data.difficulty_level ? {
                        1: 'easy',
                        2: 'medium',
                        3: 'hard',
                        4: 'hard'
                    }[data.difficulty_level] : null,
                    estimated_time_minutes: data.estimated_time_minutes,
                    tags: (questionPayload.is_manual || String(questionPayload.id || '').startsWith('manual-')) ? ['手動新增'] : [],
                    unit_id: data.unit_id === undefined ? unitId : data.unit_id,
                    kp_id: finalKpId
                })
            );

            // Reload Question Bank Panel
            if (questionBankRef.current) {
                questionBankRef.current.reload();
            }

            // Update local state with saved_question_bank_id
            // We need to track the updated content to persist it
            let updatedContentForPersist: any = null;

            setResult(prev => {
                if (!prev || !prev.content) return prev;

                // Deep clone to modify nested content
                const newContent = JSON.parse(JSON.stringify(prev.content));
                const contentBlob = newContent.content || newContent;

                // Replicate ContentRenderer's flattening logic to find the correct item by index
                let flatRefs: any[] = [];

                const processItems = (items: any[]) => {
                    items.forEach(item => {
                        if (item.questions && Array.isArray(item.questions)) {
                            // It's a block
                            item.questions.forEach((q: any) => flatRefs.push(q));
                        } else {
                            flatRefs.push(item);
                        }
                    });
                };

                if (Array.isArray(contentBlob)) {
                    processItems(contentBlob);
                } else if (contentBlob && Array.isArray(contentBlob.content)) {
                    processItems(contentBlob.content);
                } else if (contentBlob && Array.isArray(contentBlob.questions)) {
                    processItems(contentBlob.questions);
                }

                if (flatRefs[bankDrawer.questionIndex!]) {
                    flatRefs[bankDrawer.questionIndex!].saved_question_bank_id = savedItem.id;
                    // ✅ Sync the kp_id as well so it persists to course content
                    if (finalKpId) {
                        flatRefs[bankDrawer.questionIndex!].kp_id = finalKpId;

                        // ✅ ALSO sync related_kps (string array) for UI display
                        const kpObj = knowledgePoints.find(kp => String(kp.id) === String(finalKpId));
                        if (kpObj) {
                            flatRefs[bankDrawer.questionIndex!].related_kps = [kpObj.name];
                        }
                    }
                }

                // Save the updated content for persistence
                updatedContentForPersist = newContent;

                return { ...prev, content: newContent };
            });

            // Persist the saved_question_bank_id to course_contents
            // Only if we are editing an existing content (not creating new)
            if (contentId && updatedContentForPersist) {
                // Small delay to ensure state update is processed (use updated content directly)
                try {
                    await authClient.put(`/api/courses/${courseId}/contents/${contentId}`, {
                        title: updatedContentForPersist.title,
                        content_type: targetType,
                        source_type: updatedContentForPersist.source_type || 'generated_content',
                        source_id: updatedContentForPersist.source_id || updatedContentForPersist.id || 0,
                        unit_id: targetUnitId ?? updatedContentForPersist.unit_id ?? 1,
                        content: {
                            content: updatedContentForPersist.content?.content || updatedContentForPersist.content
                        }
                    });
                } catch (persistError) {
                    console.error('Failed to persist saved_question_bank_id:', persistError);
                    // Don't show error to user, the main operation succeeded
                }
            }

            setToast({ show: true, message: isUpdate ? '已更新題庫' : '已加入題庫', type: 'success' });

            // ✅ Close edit mode on the card (exits editing state on the left)
            if (rendererRef.current) {
                rendererRef.current.stopEditing();
            }

            setBankDrawer(prev => ({ ...prev, isOpen: false }));
        } catch (error) {
            console.error(error);
            setToast({ show: true, message: isUpdate ? '更新題庫失敗' : '加入題庫失敗', type: 'error' });
        }
    };

    // Ensure exclusive drawer: Close bank drawer if opening reference
    // Also records source preview logs on open/close for research analysis
    const previewOpenTimeRef = useRef<{ time: number; start: string } | null>(null);

    // Keep mirror refs in sync so the fire-and-forget effect always reads fresh values
    useEffect(() => { selectedChunkRef.current = selectedChunk; }, [selectedChunk]);
    useEffect(() => { selectedQuestionIdRef.current = selectedQuestionId; }, [selectedQuestionId]);
    useEffect(() => { resultRef.current = result; }, [result]);
    useEffect(() => { refSourceTypeRef.current = refSourceType; }, [refSourceType]);

    useEffect(() => {
        if (showReferenceModal) {
            setBankDrawer(prev => ({ ...prev, isOpen: false }));
            previewOpenTimeRef.current = {
                time: Date.now(),
                start: new Date().toISOString()
            };
        } else if (previewOpenTimeRef.current) {
            // Drawer just closed: fire log immediately (fire-and-forget)
            // Read from refs to get current values, not stale closure captures
            const viewSeconds = Math.floor((Date.now() - previewOpenTimeRef.current.time) / 1000);
            const viewStart = previewOpenTimeRef.current.start;
            const chunk = selectedChunkRef.current;
            // source_id maps to rag_documents.unique_content_id = chunk.source_metadata.document_id
            // Fall back chain: source_metadata.document_id -> unique_content_id -> source_id (on chunk root)
            const chunkSourceId: number | null = (
                (chunk as any)?.source_metadata?.document_id ??
                (chunk as any)?.unique_content_id ??
                (chunk as any)?.source_id ??
                null
            ) || null;
            const chunkId = (chunk as any)?.chunk_id ?? (chunk as any)?.id ?? null;
            const questionIdSnapshot = selectedQuestionIdRef.current;
            const refType = refSourceTypeRef.current; // 'question' | 'section' | null
            const currentResult = resultRef.current;
            previewOpenTimeRef.current = null;

            // course_content_id: always set when editing an existing content
            const courseContentIdForLog = isEditing && contentId ? parseInt(contentId) : null;

            // generated_content_id: only when source_type is explicitly 'generated_content',
            // or for brand-new generations not yet saved
            const generatedContentId = (() => {
                if (!currentResult?.content) return null;
                if ((currentResult.content as any).source_type === 'generated_content') {
                    return (currentResult.content as any).source_id || null;
                }
                if (!isEditing && currentResult.content.id) {
                    return currentResult.content.id;
                }
                return null;
            })();

            // Route the id into the semantically correct field
            const sectionIdForLog = refType === 'section' ? (questionIdSnapshot !== null ? questionIdSnapshot : null) : null;
            const questionIdForLog = refType === 'question' ? (questionIdSnapshot !== null ? questionIdSnapshot : null) : null;

            if (generatedContentId || courseContentIdForLog) {
                console.log('[ContentEditor] Logging source_preview:', {
                    course_content_id: courseContentIdForLog,
                    generated_content_id: generatedContentId,
                    source_id: chunkSourceId,
                    chunk_id: chunkId,
                    section_id: sectionIdForLog,
                    question_id: questionIdForLog,
                    view_seconds: viewSeconds
                });

                authClient.post('/api/teacher/logs/source_preview', {
                    generated_content_id: generatedContentId,
                    course_content_id: courseContentIdForLog,
                    source_id: chunkSourceId,
                    chunk_id: chunkId,
                    section_id: sectionIdForLog,
                    question_id: questionIdForLog,
                    view_start: viewStart,
                    view_seconds: viewSeconds
                }).catch(err => console.error('[ContentEditor] source_preview log failed:', err));
            } else {
                console.warn('[ContentEditor] source_preview skipped: no valid content ID', {
                    isEditing, contentId, hasResult: !!currentResult
                });
            }
        }
    }, [showReferenceModal]);




    const handleRemoveFromBank = async (idx: number, id: number) => {
        if (!confirm('確定要從題庫中移除此題目嗎？')) return;

        try {
            await authClient.delete(`/api/courses/${courseId}/question-bank/${id}`);

            // Update local state
            setResult(prev => {
                if (!prev || !prev.content) return prev;
                const newContent = JSON.parse(JSON.stringify(prev.content));
                const contentBlob = newContent.content || newContent;
                let flatRefs: any[] = [];
                const processItems = (items: any[]) => {
                    items.forEach(item => {
                        if (item.questions && Array.isArray(item.questions)) {
                            item.questions.forEach((q: any) => flatRefs.push(q));
                        } else {
                            flatRefs.push(item);
                        }
                    });
                };

                if (Array.isArray(contentBlob)) {
                    processItems(contentBlob);
                } else if (contentBlob && Array.isArray(contentBlob.content)) {
                    processItems(contentBlob.content);
                } else if (contentBlob && Array.isArray(contentBlob.questions)) {
                    processItems(contentBlob.questions);
                }

                if (flatRefs[idx]) {
                    delete flatRefs[idx].saved_question_bank_id;
                }

                if (includeInGrade) {
                    const newContentForGrading = { content: { content: newContent.content || newContent } };
                    const parsed = parseQuestionsFromContent(newContentForGrading);
                    if (parsed.questions.length > 0) {
                        const { questions, types } = distributePoints(parsed.questions, gradingConfig.total_points || 100);
                        setGradingConfig(prevConfig => ({
                            ...prevConfig,
                            grading_method: 'by_question_type',
                            question_types: types,
                            individual_questions: questions
                        }));
                    }
                }
                return { ...prev, content: newContent };
            });
            setToast({ show: true, message: '已從題庫移除', type: 'success' });
        } catch (error) {
            console.error(error);
            setToast({ show: true, message: '移除失敗（可能已被使用）', type: 'error' });
        }
    };

    const handleEditBankQuestion = async (idx: number, question: any) => {
        if (!question.saved_question_bank_id) return;

        try {
            // 獲取完整題庫資料
            const response = await fetch(
                `${API_BASE_URL}/api/courses/${courseId}/question-bank/${question.saved_question_bank_id}`
            );

            if (!response.ok) throw new Error('Failed to fetch question');
            const bankData = await response.json();

            setBankDrawer({
                isOpen: true,
                isCollapsed: false,
                questionIndex: idx,
                question: question,
                bankData: bankData  // 完整的題庫資料
            });
            setShowReferenceModal(false);
        } catch (error) {
            console.error(error);
            setToast({ show: true, message: '無法載入題目資料', type: 'error' });
        }
    };

    // Manual Question Creation Handler
    const handleAddManualQuestion = (type: 'multiple_choice' | 'short_answer' | 'fill_in_the_blank' | 'true_false') => {
        if (!result || !result.content) return;


        // Calculate the new index for the question (current length)
        let currentContent: any[] = [];

        // Handle both flattened (Array) and nested (Object) structures
        if (Array.isArray(result.content.content)) {
            currentContent = result.content.content;
        } else if (result.content.content && Array.isArray(result.content.content.content)) {
            currentContent = result.content.content.content;
        }

        const newIndex = currentContent.length;

        const newQuestion = {
            id: Math.floor(Date.now() / 1000) + Math.floor(Math.random() * 1000000), // Numeric ID
            is_manual: true,
            type,
            question_type: type,
            question_text: '',
            question_number: newIndex + 1,
            related_kps: [],
            detailed_explanation: '',
            ...(type === 'multiple_choice' && {
                options: { A: '', B: '', C: '', D: '' },
                correct_answer: ''
            }),
            ...(type === 'short_answer' && {
                sample_answer: ''
            }),
            ...(type === 'fill_in_the_blank' && {
                correct_answer: ''
            }),
            ...(type === 'true_false' && {
                correct_answer: 'true', // Default to true
                options: { true: '', false: '' } // Standard display options
            })
        };

        // Add question to content
        setResult(prev => {
            if (!prev || !prev.content) return prev;
            const newContent = JSON.parse(JSON.stringify(prev.content));

            if (Array.isArray(newContent.content)) {
                // If it's already an array, push directly
                newContent.content.push(newQuestion);
            } else {
                if (!newContent.content) {
                    newContent.content = { content: [] };
                }
                if (!newContent.content.content) {
                    newContent.content.content = [];
                }

                if (Array.isArray(newContent.content.content)) {
                    newContent.content.content.push(newQuestion);
                }
            }

            // Auto-recalculate grading if enabled
            if (includeInGrade) {
                const parsed = parseQuestionsFromContent(newContent);
                if (parsed.questions.length > 0) {
                    const totalPoints = gradingConfig.total_points || 100;
                    const { questions, types } = distributePoints(parsed.questions, totalPoints);
                    const hasRemainder = totalPoints % parsed.questions.length !== 0;

                    setGradingConfig(prevConfig => ({
                        ...prevConfig,
                        grading_method: hasRemainder ? 'by_individual_question' : 'by_question_type',
                        question_types: types,
                        individual_questions: questions
                    }));
                }
            }

            return { ...prev, content: newContent };
        });

        // Scroll to new question and auto-edit
        setTimeout(() => {
            setFocusIndex(newIndex);
            setAutoEditIndex(newIndex);
            // Reset autoEditIndex after triggering to allow future triggers
            setTimeout(() => setAutoEditIndex(null), 500);
        }, 100);


    };



    const handleReferenceClick = (chunkId: number | string, evidence: string, matchScore?: number, fullChunk?: any, qid?: number, refType?: 'question' | 'section') => {
        setSelectedQuestionId(qid !== undefined ? qid : null);
        setRefSourceType(refType || null);

        // Helper to find retrieved_text_chunks recursively in any depth
        const findChunksDeep = (obj: any, depth = 0): any[] => {
            if (!obj || typeof obj !== 'object' || depth > 5) return [];

            // Direct match
            if (Array.isArray(obj.retrieved_text_chunks)) return obj.retrieved_text_chunks;

            // Search in properties

            // Prioritize 'content' property
            if (obj.content) {
                const res = findChunksDeep(obj.content, depth + 1);
                if (res.length > 0) return res;
            }

            return [];
        };

        // 1. Extract Chunks and Pages from result to find full content
        let chunks: any[] = [];
        let pages: any[] = [];

        // Helper to extract arrays from potential locations
        const extractData = (root: any) => {
            // 0. Top-level Check
            if (Array.isArray(root?.retrieved_text_chunks)) chunks = root.retrieved_text_chunks;
            if (Array.isArray(root?.retrieved_page_content)) pages = root.retrieved_page_content;

            // 1. Direct Result Wrapper
            if (root?.content) {
                if (Array.isArray(root.content.retrieved_text_chunks)) chunks = root.content.retrieved_text_chunks;
                if (Array.isArray(root.content.retrieved_page_content)) pages = root.content.retrieved_page_content;

                // 2. Nested Content (JSON)
                if (root.content.content) {
                    if (Array.isArray(root.content.content.retrieved_text_chunks)) chunks = root.content.content.retrieved_text_chunks;
                    if (Array.isArray(root.content.content.retrieved_page_content)) pages = root.content.content.retrieved_page_content;

                    // 3. Deep Nested
                    if (root.content.content.content) {
                        if (Array.isArray(root.content.content.content.retrieved_text_chunks)) chunks = root.content.content.content.retrieved_text_chunks;
                        if (Array.isArray(root.content.content.content.retrieved_page_content)) pages = root.content.content.content.retrieved_page_content;
                    }
                }
            }
        };

        extractData(result);

        // Fallback to deep search if still empty
        if (chunks.length === 0) chunks = findChunksDeep(result?.content);

        // Use loose equality to handle potential string/number mismatches in IDs
        const globalChunk = chunks.find((c: any) => c.chunk_id == chunkId);

        // Priority:
        // 1. Global Chunk (contains full text & valid metadata from RAG result)
        // 2. Full Chunk (passed from Argument, might be incomplete if from old generation)
        const chunk = globalChunk || fullChunk;

        if (chunk) {
            // Find corresponding Full Page Content
            // Need document_id and page_number
            let targetPage = null;
            const docId = chunk.source_metadata?.document_id;
            // Use logical OR to get first valid page (chunk might span multiple, usually first is best)
            // But chunks usually have 'page' (single) or 'source_pages' (list)
            const pageNum = chunk.source_metadata?.page;

            if (docId && pageNum && pages.length > 0) {
                targetPage = pages.find((p: any) =>
                    p.source_document_id == docId && p.page_number == pageNum
                );
            }

            let displayChunk = chunk;

            // If we found the full page, use its content instead of the partial chunk text
            if (targetPage && Array.isArray(targetPage.content)) {
                // Reconstruct text for the viewer
                // Text + <圖片描述>Image Caption</圖片描述>
                let fullText = "";
                targetPage.content.forEach((item: any) => {
                    if (item.type === 'text') {
                        fullText += item.content + "\n\n";
                    } else if (item.type === 'image') {
                        // Use special tag for ReferenceDrawer parser
                        const caption = item.caption || item.vision_description || "Image";
                        fullText += `<圖片描述>${caption}</圖片描述>\n\n`;
                    }
                });

                // Create synthetic chunk with full page content
                displayChunk = {
                    ...chunk,
                    text: fullText
                };
            }

            // If clicking the same chunk that is already open, toggle it closed
            if (showReferenceModal && selectedChunk?.chunk_id === chunk.chunk_id) {
                setShowReferenceModal(false);
                return;
            }

            setSelectedChunk(displayChunk);
            setSelectedEvidence(evidence); // Legacy arg, kept for signature compatibility
            setSelectedMatchScore(matchScore);
            setShowReferenceModal(true);
        } else {
            console.warn(`Chunk ${chunkId} not found in retrieved chunks.`);
            setToast({ show: true, message: `無法顯示引用來源 (找不到 Chunk ID: ${chunkId})`, type: 'error' });
        }
    };

    const handleFeedbackSubmit = async (chunkId: number | string, rating: number, comment: string, errorTypes: string[]) => {
        try {
            console.log("[DEBUG] Feedback Submission Trace:", {
                QID: selectedQuestionId,
                jobId
            });

            await authClient.post('/api/v1/feedback/reference', {
                chunk_id: chunkId,
                rating,
                comment,
                error_types: errorTypes,
                question_id: selectedQuestionId
            });

            setToast({ show: true, message: '感謝您的回饋！', type: 'success' });
        } catch (error) {
            console.error("Feedback error:", error);
            setToast({ show: true, message: '回饋提交失敗', type: 'error' });
            throw error;
        }
    };

    const handleAddKnowledgePoint = async (name: string) => {
        const unitId = targetUnitId || urlUnitId || (result as any)?.unit_id || 1;
        try {
            const newKP = await authClient.post<any>(`/api/courses/${courseId}/units/${unitId}/kps`, { name });
            setKnowledgePoints(prev => [...prev, {
                ...newKP,
                category: 'unit'
            }]);
            return newKP;
        } catch (e: any) {
            console.error(e);
            setToast({ show: true, message: `新增知識點失敗: ${e.message || '未知錯誤'}`, type: 'error' });
            return null;
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-white flex items-center justify-center">
                <div className="flex flex-col items-center justify-center animate-in fade-in duration-1000">
                    {result?.current_avatar ? (
                        <div className="relative mb-12">
                            <img
                                src={`/images/mascots/${result.current_avatar}`}
                                alt="AI Assistant"
                                className="w-80 h-80 object-contain relative z-10 mix-blend-multiply"
                                onError={(e) => {
                                    (e.target as HTMLImageElement).style.display = 'none';
                                }}
                            />
                        </div>
                    ) : (
                        <div className="mb-12">
                            <FaSpinner className="animate-spin text-theme-primary" size={64} />
                        </div>
                    )}

                    {result?.status !== 'completed' && result?.status !== 'failed' && (
                        <div className="text-center">
                            {result?.current_step_desc ? (
                                <h3 className="text-3xl font-bold text-theme-primary animate-pulse tracking-tight">
                                    {result.current_step_desc}
                                </h3>
                            ) : (
                                <p className="text-2xl text-neutral-text-secondary font-medium">
                                    正在同步 AI 思考狀態...
                                </p>
                            )}
                        </div>
                    )}
                </div>
            </div>
        );
    }

    if (result?.status === 'failed') {
        return (
            <div className="min-h-screen bg-gray-50 p-6">
                <div className="max-w-4xl mx-auto">
                    <div className="bg-white rounded-xl border border-red-200 p-8 text-center">
                        <FaTimesCircle className="text-red-500 mx-auto mb-4" size={48} />
                        <h2 className="text-xl font-bold text-neutral-text-main mb-2">生成失敗</h2>
                        <p className="text-neutral-text-secondary mb-6">{result.error || '未知錯誤'}</p>
                        <div className="flex gap-3 justify-center">
                            <Button
                                variant="secondary"
                                onClick={() => navigate(`/teacher/courses/${courseId}`)}
                                idleText="返回課程"
                            />
                            <Button
                                variant="primary"
                                onClick={() => navigate(`/teacher/courses/${courseId}/generate?type=${targetType}&unit_id=${targetUnitId}`)}
                                idleText="重新生成"
                            />
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    if (!result?.content) return <div>No content data</div>;

    const showGrading = targetType === 'exam';

    return (
        <div className="min-h-screen bg-gray-50 flex flex-col">
            <div className="w-full mx-auto px-4 sm:px-6 pt-4 pb-12 flex-1">
                {/* Main Content Grid */}
                <div className="grid grid-cols-1 lg:grid-cols-[7fr_3fr] gap-6">
                    {/* Left Column - Header + Content */}
                    <div className="space-y-6 min-w-0">
                        {/* Header */}
                        {/* Header */}
                        <div className="p-2 mb-2 relative z-10">
                            <div className="flex items-center gap-3">
                                <div className="flex items-center justify-center w-14 h-14 shrink-0">
                                    {isEditing ? (
                                        <FaFilePen className="text-blue-600 w-12 h-12" />
                                    ) : isNewMode ? (
                                        <FaFileCirclePlus className="text-blue-600 w-12 h-12" />
                                    ) : (
                                        <FaFileCircleCheck className="text-green-500 w-12 h-12" />
                                    )}
                                </div>
                                <div>
                                    <h1 className="text-xl font-bold text-neutral-text-main flex items-center gap-2">
                                        {isEditing ? '編輯內容' : isNewMode ? `新增${targetType === 'material' ? '教材' : '試卷'}` : '生成完成 !'}
                                    </h1>
                                    <p className="text-neutral-text-secondary mt-1">
                                        {(() => {
                                            const targetUnit = units.find(u => u.id === targetUnitId);
                                            const unitText = targetUnit ? `第${targetUnit.topic_id}章 ${targetUnit.name}` : '';
                                            const typeName = targetType === 'material' ? '教材' : '考試';

                                            if (isNewMode && isManualMode) {
                                                return '請從右側面板選擇題型以新增題目，或從題庫中選取現有題目。';
                                            } else if (isNewMode) {
                                                return '請確認以下內容並設定配分，完成後請點擊儲存。';
                                            } else if (isEditing) {
                                                return `您可以調整內容與設定，確認後點擊「更新內容」，即可更新至課程內容：${unitText}。`;
                                            } else {
                                                return `建議您花些時間檢查與調整內容細節，確認後點擊「儲存為${typeName}」，即可將其加入課程內容: ${unitText}`;
                                            }
                                        })()}
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Content Card */}
                        <div className="bg-white/50 backdrop-blur-md rounded-xl border border-neutral-border p-8 shadow-sm min-h-[500px]">
                            <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-100 gap-4 relative z-[110]">
                                <div className="flex-1 pr-4 md:max-w-[calc(100%-16rem)] relative">
                                    <label className="text-xs font-bold text-gray-500 block mb-1">
                                        {targetType === 'material' ? '教材標題' : '試卷標題'}
                                    </label>
                                    {isTitleFocused ? (
                                        <input
                                            autoFocus
                                            type="text"
                                            value={result.content.title}
                                            onChange={(e) => {
                                                setResult({
                                                    ...result,
                                                    content: {
                                                        ...result.content,
                                                        title: e.target.value
                                                    } as any
                                                });
                                            }}
                                            onBlur={() => setIsTitleFocused(false)}
                                            onKeyDown={(e) => {
                                                if (e.key === 'Enter') setIsTitleFocused(false);
                                            }}
                                            className="text-2xl font-bold text-neutral-text-main w-full border-b border-theme-primary bg-transparent focus:outline-none transition-colors px-1 -ml-1 h-auto py-1"
                                        />
                                    ) : (
                                        <div
                                            onClick={() => setIsTitleFocused(true)}
                                            className="cursor-text text-2xl font-bold text-neutral-text-main w-full border-b border-transparent hover:border-gray-300 transition-colors px-1 -ml-1 h-auto py-1 min-h-[40px] flex items-center"
                                        >
                                            <ReactMarkdown
                                                remarkPlugins={[remarkGfm]}
                                                components={{
                                                    p: ({ children }) => <>{children}</>
                                                }}
                                            >
                                                {result.content.title || ''}
                                            </ReactMarkdown>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Description editable below title for all exam/assignment types */}
                            {targetType !== 'material' && (
                                <div className="mb-6 pb-6 border-b border-gray-100">
                                    <label className="text-sm font-semibold text-gray-700 block mb-2">說明 <span className="font-normal text-gray-400 text-xs">(選填)</span></label>
                                    <RichTextEditor
                                        value={publishingSettings.description || ''}
                                        onChange={(value) => setPublishingSettings(prev => ({ ...prev, description: value || null }))}
                                        placeholder="請輸入說明、作答指示、評分標準等..."
                                    />
                                </div>
                            )}

                            {/* File Upload Assignment: show FileSubmissionsPanel instead of ContentRenderer */}
                            {publishingSettings.assignment_type === 'file_upload' ? (
                                <>
                                    {contentId ? (
                                        <FileSubmissionsPanel
                                            contentId={Number(contentId)}
                                            contentTitle={result.content.title}
                                            totalPoints={(result.content as any).total_points || 100}
                                        />
                                    ) : (
                                        <div className="flex flex-col items-center justify-center py-16 text-gray-400 gap-3">
                                            <span className="text-4xl">💾</span>
                                            <p className="text-sm">儲存後才能看到繳交記錄</p>
                                        </div>
                                    )}
                                </>
                            ) : (
                                <ContentRenderer
                                    ref={rendererRef}
                                    content={result.content.content}
                                    editable={true}
                                    focusIndex={focusIndex}
                                    autoEditIndex={autoEditIndex}
                                    gradingConfig={showGrading ? gradingConfig : undefined}
                                    courseId={courseId}
                                    unitId={targetUnitId || urlUnitId || undefined}
                                    isTeacher={true}
                                    onKPLookup={handleKPLookup}
                                    onScoreChange={(idx, newScore) => {
                                        setGradingConfig(prev => {
                                            const currentQuestions = prev.individual_questions || [];
                                            const newIndividual = currentQuestions.map((q, i) =>
                                                i === idx ? { ...q, points: newScore } : q
                                            );
                                            return {
                                                ...prev,
                                                individual_questions: newIndividual
                                            };
                                        });
                                    }}
                                    onContentChange={(newContent) => {
                                        setResult({
                                            ...result,
                                            content: {
                                                ...result.content,
                                                content: newContent
                                            } as any
                                        });
                                        setContentVersion(v => v + 1);
                                    }}
                                    onReferenceClick={handleReferenceClick}
                                    onAddToBank={handleAddToBank}
                                    onRemoveFromBank={handleRemoveFromBank}
                                    onEditBankQuestion={handleEditBankQuestion}
                                    onSaveComplete={async (idx, updatedQuestion) => {
                                        // 儲存後先觸發 metadata 保存（如果有），然後關閉 drawer
                                        if (bankDrawer.isOpen && bankDrawer.questionIndex === idx) {
                                            // Store latest content in ref for the subsequent submit call to use
                                            latestQuestionRef.current = updatedQuestion;

                                            // Trigger metadata save via ref
                                            if (drawerRef.current) {
                                                await drawerRef.current.submit();
                                            }

                                            // Clear ref and close drawer
                                            latestQuestionRef.current = null;
                                            setBankDrawer({ isOpen: false, isCollapsed: false, questionIndex: null, question: null });
                                        }
                                    }}
                                    onCancelEdit={(idx) => {
                                        // If we cancel the edit, and the drawer is open for this item 
                                        // (meaning we likely auto-opened it for "Add to Bank"), close the drawer.
                                        if (bankDrawer.isOpen && bankDrawer.questionIndex === idx) {
                                            setBankDrawer({ isOpen: false, isCollapsed: false, questionIndex: null, question: null });
                                        }
                                    }}
                                    availableKPs={memoizedAvailableKPs}
                                    onAddKP={handleAddKnowledgePoint}
                                />)}

                            {(!((result.content.content as any)?.content?.length) && isNewMode) && publishingSettings.assignment_type !== 'file_upload' && (
                                <div className="flex flex-col items-center justify-center p-8 border-2 border-dashed border-gray-200 rounded-xl bg-gray-50/50 mb-6">
                                    <h3 className="text-lg font-medium text-gray-600 mb-1">尚未新增任何題目</h3>
                                    <p className="text-gray-500 text-sm">請使用下方按鈕新增題目或從題庫選題</p>
                                </div>
                            )}

                            {/* Persistent Add Question Buttons (Only for Exam, not file_upload) */}
                            {(targetType === 'exam') && publishingSettings.assignment_type !== 'file_upload' && (
                                <div className="mt-8 pt-6 border-t border-gray-100">
                                    <h4 className="text-sm font-bold text-gray-500 mb-3 flex items-center gap-2">
                                        <FaPlus className="text-blue-500" />
                                        新增題目
                                    </h4>
                                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                        <button
                                            onClick={() => handleAddManualQuestion('multiple_choice')}
                                            className="px-4 py-3 bg-white border border-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-blue-50 hover:border-blue-200 hover:text-blue-600 transition-all flex items-center justify-center gap-2 shadow-sm"
                                        >
                                            <span className="w-2 h-2 rounded-full bg-blue-400"></span>
                                            選擇題
                                        </button>
                                        <button
                                            onClick={() => handleAddManualQuestion('short_answer')}
                                            className="px-4 py-3 bg-white border border-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-green-50 hover:border-green-200 hover:text-green-600 transition-all flex items-center justify-center gap-2 shadow-sm"
                                        >
                                            <span className="w-2 h-2 rounded-full bg-green-400"></span>
                                            簡答題
                                        </button>
                                        <button
                                            onClick={() => handleAddManualQuestion('true_false')}
                                            className="px-4 py-3 bg-white border border-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-orange-50 hover:border-orange-200 hover:text-orange-600 transition-all flex items-center justify-center gap-2 shadow-sm"
                                        >
                                            <span className="w-2 h-2 rounded-full bg-orange-400"></span>
                                            是非題
                                        </button>
                                        <button
                                            onClick={() => handleAddManualQuestion('fill_in_the_blank')}
                                            className="px-4 py-3 bg-white border border-gray-200 text-gray-700 rounded-lg text-sm font-medium hover:bg-purple-50 hover:border-purple-200 hover:text-purple-600 transition-all flex items-center justify-center gap-2 shadow-sm"
                                        >
                                            <span className="w-2 h-2 rounded-full bg-purple-400"></span>
                                            填空題
                                        </button>
                                        {/* Future expansion for other types */}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Right Panel - Unified Design */}
                    <div className="space-y-6 min-w-0">
                        <div className="sticky top-4 h-[calc(100vh-6rem)] flex flex-col gap-4">
                            {/* Dynamic Right Panel Content */}
                            {(() => {
                                const hasCritic = !!criticEvaluation;
                                const showGradingPanel = targetType === 'exam';

                                // Material Mode
                                // Material Mode - No grading, just show critic/prompt (now with tabs)
                                if (!showGradingPanel) {
                                    const materialTabs = [
                                        // Critic Tab (Only if not editing or has job_id for testing)
                                        ...((!isEditing || (result?.job_id && result.job_id > 0)) ? [{
                                            id: 'critic',
                                            label: 'AI 品質評估',
                                            icon: <FaRobot />,
                                            activeColorClass: 'text-green-600 border-b-2 border-green-600 bg-green-50/50',
                                            content: hasCritic ? (
                                                <CriticResultPanel
                                                    className="h-full"
                                                    jobId={result?.job_id || 0}
                                                    evaluationData={criticEvaluation}
                                                    isLoading={isEvaluating}
                                                    onRefresh={handleTriggerEvaluation}
                                                />
                                            ) : (
                                                <EvaluationPromptPanel
                                                    className="h-full"
                                                    onEvaluate={handleTriggerEvaluation}
                                                    isEvaluating={isEvaluating}
                                                />
                                            )
                                        }] : []),
                                        // Publish Settings Tab (Always)
                                        {
                                            id: 'publish',
                                            label: '發布設定',
                                            icon: <FaCalendarAlt />,
                                            activeColorClass: 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50',
                                            content: (
                                                <div className="p-6 h-full overflow-y-auto">
                                                    <PublishSettingsPanel
                                                        contentType={targetType}
                                                        settings={publishingSettings}
                                                        onSettingsChange={setPublishingSettings}
                                                        includeInGrade={false} // Material has no grade
                                                    />
                                                </div>
                                            )
                                        }
                                    ];

                                    return (
                                        <RightPanelTabs
                                            className="flex-1 min-h-0 bg-white/50 backdrop-blur-md"
                                            tabs={materialTabs}
                                            defaultTab={isEditing ? 'publish' : 'critic'}
                                            activeTab={activeRightTab}
                                            onChange={(tabId) => setActiveRightTab(tabId as any)}
                                        />
                                    );
                                }

                                // Exam Mode
                                if (showGradingPanel) {
                                    const criticCount = questionCritics.length;

                                    return (
                                        <RightPanelTabs
                                            className="flex-1 min-h-0 bg-white/50 backdrop-blur-md"
                                            tabs={[
                                                ...((isEditing || isNewMode) && !publishingSettings.assignment_type?.startsWith('file') ? [{
                                                    id: 'bank',
                                                    label: '題庫',
                                                    icon: <FaDatabase />,
                                                    activeColorClass: 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50',
                                                    content: (
                                                        <div className="h-full flex flex-col relative w-full overflow-hidden">
                                                            <QuestionBankPanel
                                                                ref={questionBankRef}
                                                                courseId={courseId!}
                                                                selectedQuestionIds={selectedQuestionIds}
                                                                onQuestionToggle={checkDuplicateAndToggle}
                                                            />
                                                        </div>
                                                    )
                                                }] : []),
                                                ...((jobId || (result?.job_id && result.job_id > 0)) ? [{
                                                    id: 'critic',
                                                    label: 'AI 品質評估',
                                                    icon: <FaRobot />,
                                                    badge: criticCount,
                                                    activeColorClass: 'text-green-600 border-b-2 border-green-600 bg-green-50/50',
                                                    content: hasCritic ? (
                                                        <CriticResultPanel
                                                            className="h-full"
                                                            jobId={parseInt(jobId || '0') || (result?.job_id || 0)}
                                                            evaluationData={criticEvaluation}
                                                            onRefresh={handleTriggerEvaluation}
                                                        />
                                                    ) : (
                                                        <EvaluationPromptPanel
                                                            className="h-full"
                                                            onEvaluate={handleTriggerEvaluation}
                                                            isEvaluating={isEvaluating}
                                                        />
                                                    )
                                                }] : []),
                                                {
                                                    id: 'publish',
                                                    label: '發布設定',
                                                    icon: <FaCalendarAlt />,
                                                    activeColorClass: 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50',
                                                    content: (
                                                        <div className="p-6 h-full overflow-y-auto">
                                                            <PublishSettingsPanel
                                                                contentType={targetType}
                                                                settings={publishingSettings}
                                                                onSettingsChange={setPublishingSettings}
                                                                includeInGrade={includeInGrade}
                                                                onIncludeInGradeChange={setIncludeInGrade}
                                                                weight={weight}
                                                                onWeightChange={setWeight}
                                                            />
                                                        </div>
                                                    )
                                                },
                                                ...(publishingSettings.assignment_type === 'file_upload' ? [] : [{
                                                    id: 'grading',
                                                    label: (
                                                        <div className="flex items-center gap-1">
                                                            <span>配分</span>
                                                            {includeInGrade ? (
                                                                <div className="w-2 h-2 rounded-full bg-green-500" title="已開啟計分"></div>
                                                            ) : (
                                                                <div className="w-2 h-2 rounded-full bg-gray-300" title="未開啟計分"></div>
                                                            )}
                                                        </div>
                                                    ),
                                                    icon: <FaCalculator />,
                                                    activeColorClass: 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50',
                                                    content: includeInGrade ? (
                                                        <div className="h-full flex flex-col">
                                                            <div className="flex-1 overflow-hidden">
                                                                <GradingEditor
                                                                    className="h-full"
                                                                    content={result?.content?.content}
                                                                    config={gradingConfig}
                                                                    version={contentVersion}
                                                                    onChange={setGradingConfig}
                                                                    onQuestionClick={(qId) => {
                                                                        const qElement = document.querySelector(`[data-question-id="${qId}"]`);
                                                                        if (qElement) {
                                                                            const index = qElement.getAttribute('data-index');
                                                                            if (index !== null) {
                                                                                setFocusIndex(null); // Reset to trigger effect if same index
                                                                                setTimeout(() => setFocusIndex(Number(index)), 10);
                                                                            }
                                                                        }
                                                                    }}
                                                                    onContentUpdate={(newContent) => {
                                                                        // Deep clone to avoid ref issues
                                                                        let processedContent = newContent;

                                                                        // Try to parse if it's a string, or just use as is
                                                                        try {
                                                                            const parsed = typeof newContent === 'string' ? JSON.parse(newContent) : newContent;
                                                                            if (Array.isArray(parsed) || (typeof parsed === 'object' && parsed !== null && (parsed.questions || parsed.content))) {
                                                                                processedContent = parsed;
                                                                            }
                                                                        } catch (e) {
                                                                            // Not JSON, stick with original
                                                                        }

                                                                        if (result) {
                                                                            setResult({
                                                                                ...result,
                                                                                content: {
                                                                                    ...result.content,
                                                                                    content: processedContent
                                                                                } as any
                                                                            });
                                                                        }
                                                                    }}
                                                                    onValidate={(res) => setIsGradingValid(res.isValid)}
                                                                    showCriticPrompt={false}
                                                                />
                                                            </div>
                                                        </div>
                                                    ) : (
                                                        <div className="flex flex-col items-center justify-center h-full w-full p-8 text-center text-gray-500 bg-gray-50/30">
                                                            <div className="w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center mb-4 text-blue-400 shadow-sm ring-1 ring-blue-100">
                                                                <FaCalculator size={24} />
                                                            </div>
                                                            <h3 className="font-bold text-gray-700 mb-2">此試卷目前設定不計分</h3>
                                                            <p className="text-sm text-gray-500 mb-6 max-w-[200px]">若啟用配分，將可設定各題分數與總分。</p>
                                                            <button
                                                                onClick={() => setIncludeInGrade(true)}
                                                                className="px-6 py-2.5 bg-blue-100 text-blue-600 rounded-lg font-bold hover:bg-blue-200 transition-colors shadow-sm flex items-center gap-2"
                                                            >
                                                                <FaCheckCircle size={14} />
                                                                啟用配分設定
                                                            </button>
                                                        </div>
                                                    )
                                                }])
                                            ]}
                                            defaultTab={isEditing ? 'publish' : 'critic'}
                                            activeTab={activeRightTab}
                                            onChange={(tabId) => setActiveRightTab(tabId as any)}
                                        />
                                    );
                                }

                                return null;
                            })()}

                            {/* Actions Footer */}
                            <div className="flex gap-4 shrink-0">
                                {!isNewMode && !isEditing && (
                                    <Tooltip content="回到設定頁面並保留剛剛的生成設定" position="top" className="flex-1">
                                        <button
                                            onClick={handleRefine}
                                            className="w-full py-3 bg-white border border-gray-300 rounded-lg text-gray-700 font-bold hover:bg-blue-50 hover:text-blue-600 hover:border-blue-200 transition-all flex items-center justify-center gap-1 shadow-sm group relative"
                                        >
                                            <IoRefreshCircle size={24} className="text-gray-400 group-hover:text-blue-500 transition-colors" />
                                            <span>重新生成</span>
                                        </button>
                                    </Tooltip>
                                )}

                                <button
                                    onClick={handleSave}
                                    disabled={saving}
                                    className="flex-1 px-4 py-3 btn-primary flex items-center justify-center gap-2 font-bold shadow-lg shadow-blue-100 disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[1.02] active:scale-[0.98] transition-all rounded-lg text-white"
                                >
                                    {saving ? <FaSpinner className="animate-spin" /> : isEditing ? <FaSave /> : <FaSave />}
                                    {isEditing ? '更新內容' : `儲存為試卷`}
                                </button>
                            </div>
                        </div>
                    </div>

                </div >
                {/* End of Grid */}
            </div >
            <Footer />

            {
                toast.show && (
                    <Toast
                        message={toast.message}
                        type={toast.type}
                        onClose={() => setToast({ ...toast, show: false })}
                    />
                )
            }
            <Modal
                isOpen={showReEvalModal}
                onClose={() => setShowReEvalModal(false)}
                title="重新評估"
                maxWidth="max-w-xl"
            >
                <EvaluationPromptPanel
                    onEvaluate={async (workflow) => {
                        setShowReEvalModal(false);
                        await handleTriggerEvaluation(workflow);
                    }}
                    isEvaluating={isEvaluating}
                    className="!h-auto !p-0 border-none shadow-none"
                />
            </Modal>

            {/* Refinement Confirmation Modal */}
            <Modal
                isOpen={showRefineConfirm}
                onClose={() => setShowRefineConfirm(false)}
                title="重新生成教材"
                maxWidth="max-w-md"
            >
                <div className="p-4">
                    <p className="text-neutral-text-main mb-6 leading-relaxed">
                        將回到參數設定頁面並保留剛剛的設定值（包含 Prompt 與知識點），確定要重新生成嗎？
                    </p>
                    <div className="flex gap-3 justify-end">
                        <Button
                            variant="secondary"
                            onClick={() => setShowRefineConfirm(false)}
                            idleText="取消"
                        />
                        <Button
                            variant="primary"
                            onClick={confirmRefine}
                            idleText="確定"
                        />
                    </div>
                </div>
            </Modal>

            {/* Reference Drawer - Overlay Mode */}
            {
                showReferenceModal && (
                    <ReferenceDrawer
                        isOpen={true}
                        onClose={() => setShowReferenceModal(false)}
                        chunk={selectedChunk}
                        evidence={selectedEvidence}
                        matchScore={selectedMatchScore}
                        jobId={jobId ? parseInt(jobId) : undefined}
                        onFeedback={handleFeedbackSubmit}
                    />
                )
            }

            {/* Question Metadata Drawer - Overlay Mode */}
            {
                bankDrawer.isOpen && (
                    <QuestionMetadataDrawer
                        ref={drawerRef}
                        isOpen={true}
                        isCollapsed={bankDrawer.isCollapsed}
                        onToggleCollapse={() => setBankDrawer(prev => ({ ...prev, isCollapsed: !prev.isCollapsed }))}
                        onClose={() => setBankDrawer({ isOpen: false, isCollapsed: false, questionIndex: null, question: null })}
                        onConfirm={handleConfirmAddToBank}
                        initialData={{
                            title: bankDrawer.bankData?.title || bankDrawer.question?.title || bankDrawer.question?.question_text || '',
                            description: bankDrawer.bankData?.description || '',
                            question_type: bankDrawer.bankData?.question_type || bankDrawer.question?.type || bankDrawer.question?.question_type || 'short_answer',
                            difficulty_level: bankDrawer.bankData?.difficulty_level
                                ? ({ 'easy': 1, 'medium': 2, 'hard': 3, 'challenge': 4 } as const)[bankDrawer.bankData.difficulty_level as 'easy' | 'medium' | 'hard' | 'challenge'] || null
                                : null,
                            estimated_time_minutes: bankDrawer.bankData?.estimated_time_minutes,
                            unit_id: bankDrawer.bankData?.unit_id || bankDrawer.question?.unit_id,
                            kp_id: bankDrawer.bankData?.kp_id || bankDrawer.question?.kp_id || (bankDrawer.question?.related_kps?.[0] ? knowledgePoints.find(kp => kp.name === bankDrawer.question.related_kps[0])?.id : null),
                            tags: bankDrawer.bankData?.tags || bankDrawer.question?.tags || []
                        }}
                        units={units}
                        isExisting={!!bankDrawer.bankData}
                    />
                )
            }


            {/* Discard Confirmation Modal */}
            <ConfirmDialog
                isOpen={showDiscardConfirm}
                onConfirm={handleDiscardConfirm}
                onCancel={() => setShowDiscardConfirm(false)}
                title="確認返回課程？"
                message={isEditing ? "您目前的修改內容將不會被儲存。確定要放棄並返回課程頁面嗎？" : "您目前的生成結果將不會被儲存。確定要放棄並返回課程頁面嗎？"}
                confirmText="不儲存並返回"
                cancelText="繼續編輯"
            />

            {/* Duplicate Question Confirmation Modal */}
            <Modal
                isOpen={isDuplicateModalOpen}
                onClose={() => {
                    setIsDuplicateModalOpen(false);
                    setPendingDuplicateQuestion(null);
                }}
                title="是否新增重複題目？"
            >
                <div className="space-y-4">
                    <p className="text-gray-600">
                        試卷中已存在相同的題目（標題或內容相同）。確定要再次新增這道題目嗎？
                    </p>
                    <div className="flex justify-end gap-3 mt-6">
                        <Button
                            variant="secondary"
                            idleText="取消"
                            onClick={() => {
                                setIsDuplicateModalOpen(false);
                                setPendingDuplicateQuestion(null);
                            }}
                        />
                        <Button
                            idleText="確定新增"
                            onClick={confirmAddDuplicate}
                        />
                    </div>
                </div>
            </Modal>

            {/* Teacher Rating Modal */}
            {
                showRatingModal && ratingContentId && (
                    <TeacherRatingModal
                        contentId={ratingContentId}
                        isOpen={showRatingModal}
                        isRegeneration={isRegenerationRating}
                        onClose={() => {
                            setShowRatingModal(false);
                            setIsRegenerationRating(false);
                            // If modal is closed without submitting (and not in regeneration mode), navigate back
                            if (!isRegenerationRating) {
                                navigate(`/teacher/courses/${courseId}`, {
                                    state: { refresh: true },
                                    replace: false
                                });
                            }
                        }}
                        onSubmitSuccess={() => {
                            setShowRatingModal(false);
                            if (isRegenerationRating) {
                                // If submitted from regeneration flow, proceed to actual regeneration
                                setIsRegenerationRating(false);
                                confirmRefine();
                            } else {
                                // Navigate after successful normal rating (save flow)
                                navigate(`/teacher/courses/${courseId}`, {
                                    state: { refresh: true },
                                    replace: false
                                });
                            }
                        }}
                    />
                )
            }
            {/* KP Lookup Modal */}
            <Modal
                isOpen={isKPLookupModalOpen}
                onClose={() => setIsKPLookupModalOpen(false)}
                title={lookupKPCount > 0
                    ? `${lookupKPName}：共有 ${lookupKPCount} 題匹配題目`
                    : `查看題庫中本知識點題目：${lookupKPName}`}
                maxWidth="max-w-4xl"
                bodyClassName="px-10 pt-8 pb-6"
            >
                {lookupKPName && (
                    <TeacherKPQuestionsView
                        courseId={courseId!}
                        kpId={
                            lookupKPId ||
                            (knowledgePoints.find(kp => kp.name === lookupKPName)?.id as unknown as number)
                        }
                        kpName={lookupKPName}
                        onCountUpdate={(count) => setLookupKPCount(count)}
                    />
                )}
            </Modal>
        </div >
    );
}
