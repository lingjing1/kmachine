// frontend/src/pages/teacher/GeneratorSettings.tsx
import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useParams, useNavigate, useLocation, useOutletContext } from 'react-router-dom';
import {
    FaLink, FaRobot, FaCheckCircle, FaTimes, FaSpinner,
    FaClipboardList, FaEye, FaPen,
    FaFileDownload, FaInfoCircle, FaTimesCircle, FaCheck, FaFileImage, FaGlobe,
    FaFilePdf, FaFileWord, FaFilePowerpoint, FaPlus,
    FaChevronDown, FaImage, FaCode,
    FaListUl, FaKeyboard, FaCheckSquare, FaPenAlt
} from 'react-icons/fa';
import { FaBookOpenReader, FaArrowLeft } from 'react-icons/fa6';
import { MdRateReview } from 'react-icons/md';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import API_BASE_URL from '../../config/api';
import { safeRandomUUID } from '../../utils/uuid';
import { ContentRenderer } from '../../components/common/ContentRenderer';
import Toast from '../../components/common/Toast';
import ConfirmDialog from '../../components/common/ConfirmDialog';
import { submitGeneratorLog } from '../../services/generatorLogApi';
import KnowledgePointPanel, { KPDetail } from '../../components/teacher/KnowledgePointPanel';
import { useUser } from '../../contexts/UserContext';
import { authClient } from '../../services/authClient';  // ✅ Phase 4: JWT 認證
import MaterialSelectionModal from '../../components/common/MaterialSelectionModal';
import { getClassWeakPoints } from '../../services/teacherDashboardApi';
import { useCallback } from 'react';
import { ActiveTimer } from '../../utils/activeTimer';

/**
 * Helper function to render text content with code block support
 * Detects [code]...[/code] tags and renders them as syntax-highlighted code blocks
 * Uses string parsing instead of Regex to avoid escaping issues
 */
function renderTextContent(content: string): React.ReactNode {
    if (!content) return null;

    // Use regex to find all code blocks: [code]...[/code]
    // flags: g (global), i (case-insensitive for tags), s (dotAll: . matches newlines)
    // We capture: 1. Text before 2. Code content 3. Remaining text (processed in next iteration)
    // However, JS regex iteration is easier with split or exec loop.

    // Regex explanation:
    // \[[\s]*code[\s]*\]        : Match [code] with optional spaces, case-insensitive
    // ([\s\S]*?)                : Match content lazy (non-greedy), including newlines
    // (?:\[[\s]*(?:\/|\\)[\s]*code[\s]*\]|$) : Match [/code] (or [\/code]) OR end of string
    const codeBlockRegex = /\[\s*code\s*\]([\s\S]*?)(?:\[\s*(?:\/|\\)[\s]*code\s*\]|$)/gi;

    const parts: React.ReactNode[] = [];
    let lastIndex = 0;
    let match;

    // We can't use matchAll because we need the index to capture text in between
    while ((match = codeBlockRegex.exec(content)) !== null) {
        // match[0] is the full match including tags
        // match[1] is the content inside
        const fullMatch = match[0];
        const codeContent = match[1];
        const startIndex = match.index;

        // 1. Add text before the code block
        if (startIndex > lastIndex) {
            const textBefore = content.substring(lastIndex, startIndex);
            if (textBefore.trim()) {
                parts.push(
                    <p key={`text-${lastIndex}`} className="text-sm text-neutral-text-main whitespace-pre-wrap leading-relaxed font-newsreader mb-3">
                        {textBefore}
                    </p>
                );
            }
        }

        // 2. Add the code block
        parts.push(
            <div key={`code-${startIndex}`} className="my-4 border border-gray-200 rounded-lg overflow-hidden bg-gray-50">
                <div className="px-3 py-2 bg-gray-100 border-b border-gray-200 flex items-center gap-2 text-xs font-semibold text-gray-600">
                    <FaCode className="text-blue-500" />
                    程式碼段落
                </div>
                <pre className="p-4 overflow-x-auto text-xs bg-gray-900 text-gray-100 leading-relaxed">
                    <code className="font-mono">{codeContent.replace(/^\n/, '').trimEnd()}</code>
                </pre>
            </div>
        );

        lastIndex = startIndex + fullMatch.length;
    }

    // 3. Add any remaining text after the last code block
    if (lastIndex < content.length) {
        const textAfter = content.substring(lastIndex);
        if (textAfter.trim()) {
            parts.push(
                <p key={`text-end-${lastIndex}`} className="text-sm text-neutral-text-main whitespace-pre-wrap leading-relaxed font-newsreader mb-3">
                    {textAfter}
                </p>
            );
        }
    }

    // If no matches found, parts will be empty, return original content
    if (parts.length === 0) {
        return (
            <p className="text-sm text-neutral-text-main whitespace-pre-wrap leading-relaxed font-newsreader">
                {content}
            </p>
        );
    }

    return parts;
}

interface MaterialOption {
    id: number;
    file_name: string;
    unique_content_id: number;
    processing_status?: 'pending' | 'in_progress' | 'completed' | 'failed';
    created_at?: string;
    file_path?: string;
    source_type?: string;
}

// Place this helper outside component or near top
interface GeneratedMaterialOption {
    id: number;
    title: string;
    content_type: string;
    content_subtype?: string | null;
    created_at: string;
    job_id?: number;
    unit_id?: number | null; // Add unit_id to show which unit content is in
    source_type?: string;
    source_id?: number;
    content?: any; // For preview
}



interface MaterialPreviewData {
    file_name: string;
    pages: Array<{
        page_number: number;
        human_text: string;
        has_images: boolean;
        structured_content?: any[];
    }>;
    structured_content?: any; // For generated content (JSON)
    download_url?: string;
}

interface GenerationParams {
    generationType: 'exam_basic' | 'summary';
    questionTypes: string[];
    questionCount: number;
    summaryDetail: 'concise' | 'standard' | 'detailed';
    materialType: 'preview' | 'review';  // Material type: preview or review
    prompt: string;
    checkItems: string[];
    maxIterations: number;
    ablationGroup?: 'naive-rag' | 'hybrid-rag' | 'kp-hybrid-rag' | '';
}

interface OutletContext {
    setBreadcrumbPaths: (paths: Array<{ name: string; path: string }>) => void;
    setHeaderActions?: (actions: React.ReactNode) => void;
}

export default function GeneratorSettings() {
    const navigate = useNavigate();
    const location = useLocation();
    const { courseId } = useParams();
    const { setHeaderActions } = useOutletContext<OutletContext>();
    const { user } = useUser();

    // --- Logging Infrastructure ---
    const sessionId = useMemo(() => {
        const state = location.state as any;
        const id = state?.sessionId || safeRandomUUID();
        console.log('[GeneratorSettings] sessionId initialization:', {
            hasState: !!state,
            stateSessionId: state?.sessionId,
            finalId: id
        });
        return id;
    }, [location.state]);
    const lastLoggedPromptRef = useRef<string>('');
    const lastSelectedSourceRef = useRef<{ key: string; added: string[] } | null>(null);
    const previewMetaRef = useRef<{
        key: string | null;
        trigger: 'select' | 'tab_switch' | 'initial';
        addedKeys?: string[];
        actions: string[];
    }>({ key: null, trigger: 'initial', actions: [] });
    // Keep refs of current state for final session logging (unmount)
    const kpDetailsRef = useRef<KPDetail[]>([]);
    const sourceKeysRef = useRef<Set<string>>(new Set());
    const paramsRefLocal = useRef<GenerationParams | null>(null);
    const [isKnowledgeMapOpen, setIsKnowledgeMapOpen] = useState(false);

    // --- Sub-Timers ---
    const promptTimer = useMemo(() => new ActiveTimer(), []);
    const previewTimer = useMemo(() => new ActiveTimer(), []);
    const kpMapTimer = useMemo(() => new ActiveTimer(), []);

    // --- Unified Session Logging ---
    const pageTimer = useMemo(() => {
        const t = new ActiveTimer();
        t.start();
        return t;
    }, []);
    const timelineRef = useRef<Array<{
        config: any;
        duration_sec?: number;
        offset_sec: number;
    }>>([]);
    const hasSubmittedRef = useRef(false);

    const submitFullSessionLog = useCallback(async (job_id: number | null = null, isFinal = false) => {
        if (hasSubmittedRef.current) return;
        if (timelineRef.current.length === 0) return;

        // If it's a final submission (like unmount or cancel), only proceed if no generation was logged
        if (isFinal && hasSubmittedRef.current) return;

        // Set flag immediately to prevent re-entry during async call
        hasSubmittedRef.current = true;

        const totalDuration = pageTimer.getElapsedSeconds();

        try {
            await submitGeneratorLog({
                session_id: sessionId,
                action_config: {
                    actions: timelineRef.current,
                    final_status: job_id ? 'generated' : 'abandoned',
                    final_settings: {
                        params: paramsRefLocal.current,
                        kp_names: kpDetailsRef.current.map(kp => kp.name),
                        source_count: sourceKeysRef.current.size
                    }
                },
                duration_sec: Number(totalDuration.toFixed(1)),
                job_id
            });
        } catch (err) {
            console.error('[GeneratorSettings] Failed to submit session log:', err);
            // Optional: Reset flag on error to allow retry, but for session logs 
            // during navigation it's usually better to just try once.
            // hasSubmittedRef.current = false; 
        }
    }, [sessionId, pageTimer]);

    const logAction = useCallback((
        action_config: Record<string, any> = {},
        duration_sec?: number,
        job_id?: number | null
    ) => {
        // Prune empty or redundant data for cleaner analysis
        const prunedConfig = { ...action_config };
        if (Array.isArray(prunedConfig.actions) && prunedConfig.actions.length === 0) delete prunedConfig.actions;
        if (Array.isArray(prunedConfig.addedKeys) && prunedConfig.addedKeys.length === 0) delete prunedConfig.addedKeys;

        // Record all actions into the timeline
        timelineRef.current.push({
            config: prunedConfig,
            duration_sec: duration_sec ? Number(duration_sec.toFixed(1)) : undefined,
            offset_sec: Number(pageTimer.getElapsedSeconds().toFixed(1))
        });

        // Special case: if we have a job_id (meaning generation complete), we can flush
        if (job_id) {
            submitFullSessionLog(job_id);
        }
    }, [pageTimer, submitFullSessionLog]);

    // 1. Initial Page Mount Log (Minimal)
    // Removed PAGE_ENTER as per user request to reduce noise

    useEffect(() => {
        return () => {
            // Flush the entire session log on unmount if not already sent
            submitFullSessionLog(null, true);
        };
    }, [submitFullSessionLog]);

    // Track Material Preview Duration
    // (Moved below activePreviewKey declaration)

    const [showCancelConfirm, setShowCancelConfirm] = useState(false);

    // 引導生成狀態 (從教材導讀 Jump 點擊過來)
    const guidedState = location.state as {
        preSelectedKPs?: string[],
        preSelectedType?: string,
        sourceContentId?: number | string
    } | null;

    useEffect(() => {
        if (guidedState?.sourceContentId) {
            const key = `uploaded:${guidedState.sourceContentId}`;
            console.log('[GeneratorSettings] Guided generation: auto-selecting source', key);
            setSelectedSourceKeys(new Set([key]));
            setActivePreviewKey(key);
        }

        if (guidedState?.preSelectedType === 'short_answer') {
            console.log('[GeneratorSettings] Guided generation: locking to short_answer');
            setParams(p => ({
                ...p,
                questionTypes: ['簡答題']
            }));
        }

    }, [guidedState, location.state]);

    // Set header actions (Cancel button)
    useEffect(() => {
        if (setHeaderActions && courseId) {
            setHeaderActions(
                <button
                    onClick={() => {
                        logAction({ action_type: 'CANCEL_CLICK', from: 'header' });
                        setShowCancelConfirm(true);
                    }}
                    className="
                            flex items-center gap-2 text-neutral-text-secondary font-medium
                            transition-all duration-200 hover:text-blue-700 group
                        "
                    title="返回課程頁面"
                >
                    <div className="w-10 h-10 rounded-xl bg-white border border-gray-200 shadow-sm flex items-center justify-center transition-all duration-200 group-hover:bg-blue-50 group-hover:border-blue-200">
                        <FaArrowLeft className="w-4 h-4 flex-shrink-0 group-hover:scale-110 transition-transform" />
                    </div>
                    <span className="max-lg:hidden whitespace-nowrap">返回課程</span>
                </button>
            );
        }
        // Cleanup on unmount
        return () => {
            if (setHeaderActions) setHeaderActions(null);
        };
    }, [courseId, setHeaderActions, logAction]);

    // Read content type from URL parameter
    const searchParams = new URLSearchParams(location.search);
    const contentType = (searchParams.get('type') || 'material') as 'material' | 'exam';

    // Type-specific configuration
    const typeConfig = {
        material: {
            title: 'AI 生成教材',
            placeholder: '例如：請使用引導式口吻說明、以列點式呈現核心概念...',
            icon: '📚'
        },
        exam: {
            title: 'AI 生成考試',
            placeholder: '例如：題目需包含情境應用題、題幹描述的更加詳細...',
            icon: '🎯'
        }
    };

    // Memoize pre-selected names to avoid infinite loops in KnowledgePointPanel
    const preSelectedNames = useMemo(() => {
        return guidedState?.preSelectedKPs || (location.state as any)?.selectedKPDetails?.map((kp: any) => kp.name) || [];
    }, [guidedState?.preSelectedKPs, (location.state as any)?.selectedKPDetails]);

    const [materials, setMaterials] = useState<MaterialOption[]>([]);
    const [generatedMaterials, setGeneratedMaterials] = useState<GeneratedMaterialOption[]>([]);
    const [courseUnits, setCourseUnits] = useState<Array<{ id: number; name: string; topic_id?: number }>>([]);
    const [courseName, setCourseName] = useState('');
    const [isGeneratedLoading, setIsGeneratedLoading] = useState(false);
    const [isGeneratedFetching, setIsGeneratedFetching] = useState(false);

    // Selection State
    const [activeTab, setActiveTab] = useState<'uploaded' | 'generated'>('uploaded');

    // Multi-select state: Set of keys "type:id"
    const [selectedSourceKeys, setSelectedSourceKeys] = useState<Set<string>>(() => {
        const state = location.state as any;
        if (state?.reconstruct && state.selectedSourceKeys) {
            return new Set(state.selectedSourceKeys);
        }
        return new Set();
    });
    // Active preview tab key
    const [activePreviewKey, setActivePreviewKey] = useState<string | null>(null);

    const [previewData, setPreviewData] = useState<MaterialPreviewData | null>(null);
    const [showFilePreview, setShowFilePreview] = useState(false);

    const prevSelectedKeysRef = useRef<Set<string>>(new Set());

    // Auto-select preview when selection changes
    useEffect(() => {
        const prevKeys = prevSelectedKeysRef.current;
        const currentKeys = selectedSourceKeys;

        if (currentKeys.size > 0) {
            const newKeys = Array.from(currentKeys).filter(key => !prevKeys.has(key));
            if (newKeys.length > 0) {
                setActivePreviewKey(newKeys[newKeys.length - 1]);
            } else if (!activePreviewKey || !currentKeys.has(activePreviewKey)) {
                const keysArray = Array.from(currentKeys);
                setActivePreviewKey(keysArray[keysArray.length - 1]);
            }
        } else {
            setActivePreviewKey(null);
            setPreviewData(null);
        }
        prevSelectedKeysRef.current = new Set(currentKeys);
    }, [selectedSourceKeys, activePreviewKey]);

    // Reset view mode when switching files
    useEffect(() => {
        setShowFilePreview(false);
    }, [activePreviewKey]);

    // Track Material Preview Session Lifecycle (Start/End on key change)
    useEffect(() => {
        if (activePreviewKey) {
            // Determine trigger
            let trigger: 'select' | 'tab_switch' | 'initial' = 'tab_switch';
            let addedKeys: string[] | undefined = undefined;

            if (lastSelectedSourceRef.current && lastSelectedSourceRef.current.key === activePreviewKey) {
                trigger = 'select';
                addedKeys = lastSelectedSourceRef.current.added;
                lastSelectedSourceRef.current = null;
            }

            previewMetaRef.current = {
                key: activePreviewKey,
                trigger,
                addedKeys,
                actions: []
            };

            previewTimer.start();
            // If map is already open, pause immediately
            if (isKnowledgeMapOpen) {
                previewTimer.manualPause();
            }
        }

        return () => {
            const duration = previewTimer.stop();
            // We use a ref copy or local activePreviewKey for consistent logging in cleanup
            // Since activePreviewKey from closure is correct for unmount/switch change
            if (activePreviewKey && duration > 0.5 && previewMetaRef.current.key === activePreviewKey) {
                logAction(
                    {
                        action_type: 'MATERIAL_PREVIEW',
                        key: activePreviewKey,
                        trigger: previewMetaRef.current.trigger,
                        addedKeys: previewMetaRef.current.addedKeys,
                        actions: previewMetaRef.current.actions
                    },
                    duration
                );
            }
            previewMetaRef.current.key = null;
        };
    }, [activePreviewKey, logAction, previewTimer]);

    // Handle Knowledge Map Overlay (Pause/Resume document timer)
    useEffect(() => {
        if (activePreviewKey) {
            if (isKnowledgeMapOpen) {
                previewTimer.manualPause();
            } else {
                previewTimer.manualResume();
            }
        }
    }, [isKnowledgeMapOpen, activePreviewKey, previewTimer]);

    // Track Knowledge Map Duration
    useEffect(() => {
        if (isKnowledgeMapOpen) {
            kpMapTimer.start();
            logAction({ action_type: 'KNOWLEDGE_MAP_OPEN' });
        } else {
            const duration = kpMapTimer.stop();
            if (duration > 0.5) {
                logAction({ action_type: 'KNOWLEDGE_MAP_CLOSE' }, duration);
            }
        }
    }, [isKnowledgeMapOpen, logAction, kpMapTimer]);

    const [previewLoading, setPreviewLoading] = useState(false);
    const [showMaterialModal, setShowMaterialModal] = useState(false);
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [textInput, setTextInput] = useState(''); // For manual text content input
    const [error, setError] = useState('');

    // KP Selection State
    const [selectedKPDetails, setSelectedKPDetails] = useState<KPDetail[]>(() => {
        const state = location.state as any;
        if (state?.reconstruct && state.selectedKPDetails) {
            return state.selectedKPDetails;
        }
        return [];
    });
    const [weakKPNames, setWeakKPNames] = useState<string[]>([]);

    // Toast state
    const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'error' | 'info' }>({ show: false, message: '', type: 'success' });

    // Confirm dialog state
    const [confirmDialog, setConfirmDialog] = useState<{ show: boolean; id: number | null }>({ show: false, id: null });

    // Preview Rename state
    const [editingPreviewName, setEditingPreviewName] = useState('');
    const [isEditingPreview, setIsEditingPreview] = useState(false);

    // Manual Input Modal state (for failed URL fallback)
    const [showManualInputModal, setShowManualInputModal] = useState(false);

    // Type-specific default parameters
    const getDefaultParams = (type: 'material' | 'exam'): GenerationParams => {
        const baseParams = {
            checkItems: ['fact', 'task', 'quality'],
            maxIterations: 1
        };

        switch (type) {
            case 'material':
                return {
                    ...baseParams,
                    generationType: 'summary',
                    questionTypes: [],
                    questionCount: 0,
                    summaryDetail: 'standard',
                    materialType: 'preview',
                    prompt: '',
                    ablationGroup: ''
                };
            case 'exam':
                return {
                    ...baseParams,
                    generationType: 'exam_basic',
                    questionTypes: [],
                    questionCount: 5,
                    summaryDetail: 'standard',
                    materialType: 'preview',
                    prompt: '',
                    ablationGroup: ''
                };
        }
    };

    const [params, setParams] = useState<GenerationParams>(() => {
        const state = location.state as any;
        const defaults = getDefaultParams(contentType);
        if (state?.reconstruct && state.params) {
            return {
                ...defaults,
                ...state.params,
                prompt: state.params.prompt || defaults.prompt
            };
        }
        return defaults;
    });

    // Effects to sync refs with state for logging infrastructure
    useEffect(() => { kpDetailsRef.current = selectedKPDetails; }, [selectedKPDetails]);
    useEffect(() => { sourceKeysRef.current = selectedSourceKeys; }, [selectedSourceKeys]);
    useEffect(() => { paramsRefLocal.current = params; }, [params]);

    // ---- Fetch Weak KPs for Review ----
    useEffect(() => {
        const unitId = new URLSearchParams(location.search).get('unit_id');
        if (params.materialType === 'review' && unitId) {
            getClassWeakPoints(parseInt(unitId), 'preview') // Fetching weak points from preview performance
                .then(data => {
                    const names = data.map(item => item.kp_name);
                    setWeakKPNames(names);
                })
                .catch(err => {
                    console.error('Failed to fetch weak points:', err);
                    setWeakKPNames([]);
                });
        } else {
            setWeakKPNames([]);
        }
    }, [params.materialType, location.search]);

    // Auto-update placeholder prompt based on detailed parameters
    const autoPrompt = useMemo(() => {
        if (params.generationType === 'exam_basic') {
            const typesStr = params.questionTypes.length > 0 ? params.questionTypes.join('、') : '混合題型';
            let p = `根據以下教材內容，生成一份包含 ${params.questionCount} 題的測驗。`;
            if (params.questionTypes.length > 0) {
                p += `題型包含：${typesStr}。`;
            }
            return p;
        } else if (params.generationType === 'summary') {
            let detailDesc = '';
            switch (params.summaryDetail) {
                case 'concise': detailDesc = '精簡的重點摘要，列點式呈現核心概念'; break;
                case 'detailed': detailDesc = '詳盡的內容解析，包含核心概念解釋、關鍵定義與實際應用範例'; break;
                case 'standard': default: detailDesc = '標準的重點整理，歸納出核心概念與關鍵術語'; break;
            }
            return `請針對教材內容進行${detailDesc}。`;
        }
        return typeConfig[contentType === 'exam' ? 'exam' : 'material'].placeholder;
    }, [params.generationType, params.questionTypes, params.questionCount, params.summaryDetail, contentType]);

    useEffect(() => {
        // Breadcrumbs are handled by Teacher parent layout based on path
    }, [courseId, contentType, courseName]);

    // Fetch data on mount
    useEffect(() => {
        fetchMaterials();
        fetchGeneratedMaterials();
        // Fetch course details to get units
        (async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}`);
                if (response.ok) {
                    const data = await response.json();
                    setCourseUnits(data.units || []);
                    setCourseName(data.name || '');
                }
            } catch (err) {
                console.error('Failed to fetch course units:', err);
            }
        })();
    }, [courseId]);

    // Polling for processing materials
    useEffect(() => {
        const hasProcessing = materials.some(m => m.processing_status === 'in_progress' || m.processing_status === 'pending');
        if (hasProcessing) {
            const timer = setTimeout(() => fetchMaterials(), 3000);
            return () => clearTimeout(timer);
        }
    }, [materials]);

    useEffect(() => {
        if (activePreviewKey) {
            const [type, idStr] = activePreviewKey.split(':');
            const id = parseInt(idStr);
            if (type === 'uploaded') {
                fetchMaterialPreview(id);
            } else if (type === 'generated') {
                // Preview data is already set by handleSourceSelect, no need to fetch again
                // This avoids calling the old /api/v1/generated_materials endpoint
            }
        } else {
            setPreviewData(null);
        }
    }, [activePreviewKey]);

    const fetchMaterials = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/v1/materials?course_id=${courseId}`);
            if (response.ok) {
                const data = await response.json();
                // Filter out failed materials and map data
                const mappedData = data
                    .filter((item: any) => item.processing_status !== 'failed')
                    .map((item: any) => ({
                        ...item,
                        file_name: item.file_name || item.name || 'Untitled'
                    }));
                setMaterials(mappedData);
            }
        } catch (err) {
            console.error('Failed to fetch materials:', err);
        }
    };



    const confirmDeleteMaterial = async () => {
        if (!confirmDialog.id) return;
        const id = confirmDialog.id;

        try {
            const response = await fetch(`${API_BASE_URL}/api/v1/materials/${id}`, { method: 'DELETE' });
            if (response.ok) {
                // Update local state immediately
                setMaterials(prev => prev.filter(m => m.id !== id));
                // Remove from selection if selected and close preview if active
                const item = materials.find(m => m.id === id);
                if (item) {
                    const key = `uploaded:${item.unique_content_id}`;

                    setSelectedSourceKeys(prev => {
                        const newSet = new Set(prev);
                        newSet.delete(key);
                        return newSet;
                    });

                    // If the deleted material is currently being previewed, close the preview
                    if (activePreviewKey === key) {
                        setActivePreviewKey(null);
                        setPreviewData(null);
                    }
                }

                setToast({ show: true, message: '刪除成功', type: 'success' });
            } else {
                setToast({ show: true, message: '刪除失敗', type: 'error' });
            }
        } catch (err) {
            console.error('Failed to delete material:', err);
            setToast({ show: true, message: '刪除失敗', type: 'error' });
        } finally {
            setConfirmDialog({ show: false, id: null });
        }
    };

    const handleRenameAction = async (id: number, newName: string) => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/v1/materials/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            });
            if (response.ok) {
                setMaterials(prev => prev.map(m => m.id === id ? { ...m, file_name: newName } : m));

                if (activePreviewKey === `uploaded:${id}` && previewData) {
                    setPreviewData({ ...previewData, file_name: newName });
                }

                setToast({ show: true, message: '更名成功', type: 'success' });
                return true;
            } else {
                setToast({ show: true, message: '更名失敗', type: 'error' });
                return false;
            }
        } catch (error) {
            console.error("Rename error:", error);
            setToast({ show: true, message: '更名發生錯誤', type: 'error' });
            return false;
        }
    };

    // Preview Rename Handlers
    const handlePreviewRenameClick = () => {
        if (previewData) {
            setEditingPreviewName(previewData.file_name);
            setIsEditingPreview(true);
        }
    };

    const handlePreviewRenameCancel = () => {
        setIsEditingPreview(false);
        setEditingPreviewName('');
    };

    const handlePreviewRenameSubmit = async () => {
        if (!activePreviewKey || !activePreviewKey.startsWith('uploaded:') || !previewData) return;

        const id = parseInt(activePreviewKey.split(':')[1]);
        if (!editingPreviewName.trim() || editingPreviewName === previewData.file_name) {
            handlePreviewRenameCancel();
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/api/v1/materials/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: editingPreviewName })
            });

            if (response.ok) {
                // Update materials list
                setMaterials(prev => prev.map(m => m.id === id ? { ...m, file_name: editingPreviewName } : m));
                // Update preview data
                setPreviewData({ ...previewData, file_name: editingPreviewName });

                setToast({ show: true, message: '更名成功', type: 'success' });
                setIsEditingPreview(false);

                // Record action in preview session
                if (previewMetaRef.current.key === activePreviewKey) {
                    previewMetaRef.current.actions.push('RENAME');
                }
            } else {
                setToast({ show: true, message: '更名失敗', type: 'error' });
            }
        } catch (error) {
            console.error("Rename error:", error);
            setToast({ show: true, message: '更名發生錯誤', type: 'error' });
        }
    };

    const fetchGeneratedMaterials = async () => {
        setIsGeneratedLoading(true);
        setIsGeneratedFetching(true);
        try {
            // Fetch from course_contents instead of generated_materials
            const response = await fetch(`${API_BASE_URL}/api/courses/${courseId}/contents`);
            if (response.ok) {
                const data = await response.json();
                // Filter by current content type and map to expected format
                const filtered = data
                    .filter((item: any) => {
                        const target = contentType.toLowerCase();
                        const itype = (item.content_type || '').toLowerCase();
                        if (target === 'material') {
                            return itype.includes('material') || itype.includes('summary');
                        }
                        return itype.includes('exam') || itype.includes('quiz') || itype.includes('test');
                    })
                    .map((item: any) => ({
                        id: item.id,
                        title: item.title,
                        content_type: item.content_type,
                        content_subtype: item.content_subtype, // Correctly include the subtype
                        created_at: item.created_at,
                        unit_id: item.unit_id,
                        source_type: item.source_type,
                        source_id: item.source_id,
                        content: item.content
                    }));
                setGeneratedMaterials(filtered);
            }
        } finally {
            setIsGeneratedLoading(false);
            setIsGeneratedFetching(false);
        }
    };

    const fetchMaterialPreview = async (uniqueContentId: number) => {
        setPreviewLoading(true);
        try {
            const response = await fetch(`${API_BASE_URL}/api/v1/materials/${uniqueContentId}/preview`);
            if (response.ok) {
                const data = await response.json();
                setPreviewData(data);
            } else {
                throw new Error("Preview failed");
            }
        } catch (err) {
            console.error('Failed to fetch preview:', err);
            // Fallback name
            let name = 'Unknown';
            const item = materials.find(m => m.unique_content_id === uniqueContentId);
            if (item) name = item.file_name;

            setPreviewData({
                file_name: name,
                pages: [{
                    page_number: 1,
                    human_text: '預覽載入失敗或內容尚未準備好。',
                    has_images: false
                }]
            });
        } finally {
            setPreviewLoading(false);
        }
    };




    /* 
    Legacy Function Removed: ingestGeneratedMaterial
    const ingestGeneratedMaterial = async (materialId: number): Promise<number | null> => { ... }
    */

    const processUpload = async (file: File) => {
        if (file.size === 0) {
            setToast({ show: true, message: '您選擇的檔案內容為空，請確認您選擇的檔案。', type: 'error' });
            return;
        }

        setUploading(true);
        setToast({ show: true, message: '開始上傳...', type: 'info' });
        const startTime = Date.now();

        const formData = new FormData();
        formData.append('file', file);
        formData.append('course_id', courseId || '1');
        // ✅ Phase 4: uploader_id 從 JWT token 自動提取，無需手動添加

        try {
            const data = await authClient.postFormData('/api/v1/ingest', formData) as { unique_content_id?: number };

            // 確保提示至少顯示 1秒
            const duration = Date.now() - startTime;
            if (duration < 1000) {
                await new Promise(resolve => setTimeout(resolve, 1000 - duration));
            }

            if (data && data.unique_content_id) {
                // Auto-select the newly uploaded item
                const newKey = `uploaded:${data.unique_content_id}`;
                setSelectedSourceKeys(prev => new Set(prev).add(newKey));
                setToast({ show: true, message: '上傳成功', type: 'success' });
            } else {
                setToast({ show: true, message: '上傳處理中', type: 'info' });
            }

            // Re-fetch materials to show the new or updated item
            fetchMaterials();
        } catch (error) {
            console.error("Upload error:", error);
            setToast({ show: true, message: `上傳發生錯誤: ${file.name}`, type: 'error' });
        } finally {
            setUploading(false);
        }
    };

    const handleUrlUpload = async (url: string) => {
        if (!url.trim()) return;
        setUploading(true);
        setToast({ show: true, message: '正在處理連結...', type: 'info' });
        const startTime = Date.now();

        const formData = new FormData();
        formData.append('url', url);
        formData.append('course_id', courseId || '1');
        // ✅ Phase 4: uploader_id 從 JWT token 自動提取

        try {
            const data = await authClient.postFormData('/api/v1/ingest', formData) as { unique_content_id?: number };
            const uniqueContentId = data.unique_content_id;

            // 確保提示至少顯示 1秒
            const duration = Date.now() - startTime;
            if (duration < 1000) {
                await new Promise(resolve => setTimeout(resolve, 1000 - duration));
            }

            // Poll for processing status (check after 3 seconds)
            setTimeout(async () => {
                try {
                    const materialsResponse = await fetch(`${API_BASE_URL}/api/v1/materials?course_id=${courseId}`);
                    if (materialsResponse.ok) {
                        const materials = await materialsResponse.json();
                        const uploadedItem = materials.find((m: any) => m.unique_content_id === uniqueContentId);

                        if (uploadedItem && uploadedItem.processing_status === 'failed') {
                            // Show guidance toast AND open manual input modal
                            setToast({
                                show: true,
                                message: '網頁抓取失敗，請嘗試手動貼上內容',
                                type: 'error'
                            });
                            setShowManualInputModal(true);
                        }
                    }
                } catch (err) {
                    console.error('Failed to check processing status:', err);
                }
            }, 3000);

            await fetchMaterials();
            setToast({ show: true, message: '已提交網址處理請求', type: 'info' });
        } catch (error) {
            console.error("URL Upload error:", error);
            setToast({ show: true, message: '連結處理錯誤，請嘗試手動輸入', type: 'error' });
            setShowManualInputModal(true);
        } finally {
            setUploading(false);
        }
    };

    const handleTextSubmit = async () => {
        if (!textInput.trim()) {
            setToast({ show: true, message: '請輸入內容', type: 'error' });
            return;
        }

        setUploading(true);
        setToast({ show: true, message: '正在處理文字內容...', type: 'info' });
        const startTime = Date.now();

        try {
            // Create a text file blob and send to ingest API
            const blob = new Blob([textInput], { type: 'text/plain' });
            const file = new File([blob], `手動輸入_${Date.now()}.txt`, { type: 'text/plain' });

            const formData = new FormData();
            formData.append('file', file);
            formData.append('course_id', courseId || '1');
            // ✅ Phase 4: uploader_id 從 JWT token 自動提取

            await authClient.postFormData('/api/v1/ingest', formData);

            // 確保提示至少顯示 1秒
            const duration = Date.now() - startTime;
            if (duration < 1000) {
                await new Promise(resolve => setTimeout(resolve, 1000 - duration));
            }

            await fetchMaterials();
            setTextInput('');
            setShowManualInputModal(false);
            setToast({ show: true, message: '文字內容已成功加入', type: 'success' });
        } catch (error) {
            console.error("Text submit error:", error);
            setToast({ show: true, message: '處理錯誤', type: 'error' });
        } finally {
            setUploading(false);
        }
    };








    const handleGenerate = async () => {
        const state = location.state as any;
        const isRegenerating = !!state?.reconstruct;

        // Prune params based on contentType
        const prunedParams = { ...params };
        if (contentType === 'material') {
            delete (prunedParams as any).questionCount;
            delete (prunedParams as any).questionTypes;
        } else if (contentType === 'exam') {
            delete (prunedParams as any).summaryDetail;
        }

        logAction(
            {
                action_type: isRegenerating ? 'REGENERATE_CLICK' : 'GENERATE_CLICK',
                contentType
            }
        );

        if (selectedSourceKeys.size === 0) {
            setError('請選擇至少一個教材');
            return;
        }

        const sourceIds: number[] = [];
        const generatedSourceIds: number[] = [];
        setLoading(true);
        setError('');

        try {
            for (const key of selectedSourceKeys) {
                const [type, idStr] = key.split(':');
                const id = parseInt(idStr);

                if (type === 'uploaded') {
                    // For uploaded content, the ID used in key is already unique_content_id
                    sourceIds.push(id);
                } else if (type === 'generated') {
                    // For generated, directly use the course_content_id
                    generatedSourceIds.push(id);
                }
            }

            if (sourceIds.length === 0 && generatedSourceIds.length === 0) {
                setError("無法處理所選的教材");
                setLoading(false);
                return;
            }

            // Prepare payload with selected KP information
            // Note: Critic is disabled during initial generation. It can be triggered manually in the result page.
            const payload: any = {
                source_ids: sourceIds,
                generated_source_ids: generatedSourceIds,
                selected_kp_ids: selectedKPDetails.map(kp => String(kp.id)),
                selected_kp_names: selectedKPDetails.map(kp => kp.name),
                prompt: (autoPrompt + (params.prompt.trim() ? '\n' + params.prompt.trim() : '')).trim(),
                user_id: user?.user_id || 1,
                critic_workflow: 1, // Workflow 1 is usually the basic generation
                mode: 'quick',      // Default mode
                max_iterations: params.maxIterations,
                content_type: contentType,
                unit_id: searchParams.get('unit_id') ? parseInt(searchParams.get('unit_id')!) : null,
                course_id: searchParams.get('course_id') ? parseInt(searchParams.get('course_id')!) : (courseId ? parseInt(courseId) : null),
                model_name: (params as any).modelName || null,
                ablation_group: params.ablationGroup || null
            };


            // Conditionally add parameters based on content type to keep job_context clean
            if (contentType === 'material') {
                payload.material_type = params.materialType;
                payload.length = params.summaryDetail;
            } else if (contentType === 'exam') {
                payload.question_types = params.questionTypes;
                payload.question_count = params.questionCount;
            }

            // console.log('📌 Generate Payload:', payload);  // Debug log
            // console.log('🔍 Length parameter details:', {
            //     'params.summaryDetail': params.summaryDetail,
            //     'params.materialType': params.materialType,
            //     'params object': params
            // });

            console.log('[GeneratorSettings] handleGenerate - Payload:', payload);

            // Always use the basic generation endpoint
            const endpoint = '/api/v1/generate';

            // ✅ Phase 4: 使用 authClient
            const data: any = await authClient.post(endpoint, payload);
            console.log('[GeneratorSettings] handleGenerate - Backend Response data:', data);

            // Log Success and flush session with job_id before navigation
            logAction({ action_type: 'GENERATE_SUCCESS', job_id: data.job_id }, undefined, data.job_id);

            const unitId = searchParams.get('unit_id');
            const includeGrading = searchParams.get('include_grading');
            const targetUrl = `/teacher/courses/${courseId}/generate/${data.job_id}?type=${contentType}${unitId ? `&unit_id=${unitId}` : ''}${includeGrading ? `&grade=${includeGrading}` : ''}`;

            console.log('[GeneratorSettings] handleGenerate - Navigating to:', targetUrl);

            navigate(
                targetUrl,
                { state: { selectedKPs: selectedKPDetails, sessionId: sessionId } }
            );
        } catch (err: any) {
            setError(err.message || '發生錯誤');
        } finally {
            setLoading(false);
        }
    };

    const selectedItemsList = Array.from(selectedSourceKeys).map(key => {
        const [type, idStr] = key.split(':');
        const id = parseInt(idStr);
        let name = 'Unknown';
        if (type === 'uploaded') {
            const item = materials.find(m => m.unique_content_id === id);
            if (item) name = item.file_name;
        } else {
            const item = generatedMaterials.find(m => m.id === id);
            if (item) name = item.title;
        }
        return { key, name, type: type as any, id };
    });

    const handleKPSelectionChange = (
        _: Set<number>,
        details: KPDetail[]
    ) => {
        setSelectedKPDetails(details);
        console.log('Selected KPs:', details);
    };

    const handleTabChange = (tab: 'uploaded' | 'generated') => {
        setActiveTab(tab);
        logAction({ action_type: 'TAB_CHANGE', tab });
    };

    const handleSourceSelectionChange = (newKeys: Set<string>) => {
        const added = Array.from(newKeys).filter(k => !selectedSourceKeys.has(k));
        const removed = Array.from(selectedSourceKeys).filter(k => !newKeys.has(k));

        if (added.length > 0) {
            const addedKey = added[0]; // Assuming one select at a time from modal clicks
            lastSelectedSourceRef.current = { key: addedKey, added: added };
            // Immediate log ACTION for selection is removed to combine with preview duration
        }
        if (removed.length > 0) logAction({ action_type: 'SOURCE_DESELECT', keys: removed });

        setSelectedSourceKeys(newKeys);
    };


    return (
        <div className="h-full bg-gradient-to-br from-gray-50 to-gray-100 overflow-hidden flex flex-col">
            {/* Material Selection Modal */}
            <MaterialSelectionModal
                isOpen={showMaterialModal}
                onClose={() => setShowMaterialModal(false)}
                activeTab={activeTab}
                onTabChange={handleTabChange}
                materials={materials}
                generatedMaterials={generatedMaterials}
                courseUnits={courseUnits}
                isLoading={isGeneratedLoading}
                isFetching={isGeneratedFetching}
                selectedKeys={selectedSourceKeys}
                onSelectionChange={handleSourceSelectionChange}
                isUploading={uploading}
                onUploadFile={processUpload}
                onUploadUrl={handleUrlUpload}
                onRename={handleRenameAction}
                onDelete={async (id) => {
                    setConfirmDialog({ show: true, id });
                    return true;
                }}
                isConfirmLoading={loading}
                title="選擇參考資料"
                confirmText="完成選擇"
            />
            {showManualInputModal && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-[1px] animate-in fade-in duration-200">
                    <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
                        <div className="px-6 py-4 bg-red-50 border-b border-red-100 flex items-center justify-between shrink-0">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center shrink-0 border border-red-200">
                                    <FaLink className="text-red-500 w-4 h-4" />
                                </div>
                                <div>
                                    <h3 className="font-bold text-gray-900">網頁抓取失敗</h3>
                                    <p className="text-xs text-red-600 mt-0.5">該網站可能有防護機制，請手動擷取網頁內容並儲存</p>
                                </div>
                            </div>
                            <button onClick={() => setShowManualInputModal(false)} className="text-gray-400 hover:text-gray-600 transition-colors">
                                <FaTimesCircle className="w-6 h-6" />
                            </button>
                        </div>
                        <div className="p-6 space-y-4 flex-1 overflow-y-auto">
                            <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-sm text-blue-800 flex gap-2">
                                <FaInfoCircle className="w-5 h-5 shrink-0 mt-0.5 opacity-70" />
                                <p>建議步驟：回到該網頁 → 全選 (Ctrl+A) → 複製 (Ctrl+C) → 在下方文字框貼上 (Ctrl+V)</p>
                            </div>
                            <textarea
                                value={textInput}
                                onChange={(e) => setTextInput(e.target.value)}
                                placeholder="請在此貼上網頁全文內容..."
                                className="w-full h-64 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-theme-primary focus:border-theme-primary outline-none resize-none text-sm leading-relaxed font-mono"
                                autoFocus
                            />
                        </div>
                        <div className="p-4 border-t border-gray-100 bg-gray-50 flex justify-end gap-3 shrink-0">
                            <button
                                onClick={() => setShowManualInputModal(false)}
                                className="px-4 py-2 text-gray-600 hover:bg-gray-200 rounded-lg text-sm font-medium transition-colors"
                            >
                                取消
                            </button>
                            <button
                                onClick={handleTextSubmit}
                                disabled={!textInput.trim() || uploading}
                                className="px-6 py-2 bg-theme-primary text-white rounded-lg hover:bg-theme-primary-dark disabled:opacity-50 text-sm font-bold shadow-sm transition-all flex items-center gap-2"
                            >
                                {uploading ? <FaSpinner className="animate-spin" /> : <FaCheckCircle />}
                                確認儲存為教材
                            </button>
                        </div>
                    </div>
                </div>
            )}


            {/* 3-Column Layout */}
            <div className="flex-1 w-full px-4 sm:px-6 pt-4 pb-4">
                <div className="grid grid-cols-12 gap-3 items-start">
                    {/* Left Column = Generation Settings */}
                    <div className="col-span-3 bg-white/50 backdrop-blur-md rounded-xl border border-neutral-border sticky top-4 min-h-[calc(100vh-6.5rem)] max-h-[calc(100vh-6.5rem)] flex flex-col p-0 overflow-hidden shadow-sm">
                        <div className="px-4 py-3 border-b border-neutral-border bg-gradient-to-r from-blue-50 to-slate-50 shrink-0">
                            <h2 className="text-lg font-bold text-blue-800 flex items-center gap-2">
                                <span className="w-8 h-8 bg-blue-100 text-blue-600 rounded-lg flex items-center justify-center font-bold">1</span>
                                生成設定
                            </h2>
                        </div>
                        {/* Generation Type & Params */}
                        <div className="p-4 overflow-y-auto custom-scrollbar flex-1">
                            {/* Render params based on contentType (not generationType) */}
                            {contentType === 'material' ? (
                                // Material Parameters
                                <div className="space-y-8">
                                    {/* Material Type Selection */}
                                    <div>
                                        <label className="block text-sm font-semibold text-neutral-text-main mb-3">教材類型</label>
                                        <div className="flex gap-2 bg-white/50 p-1.5 rounded-lg border border-neutral-border shadow-sm">
                                            <button
                                                onClick={() => {
                                                    setParams({ ...params, materialType: 'preview' });
                                                    logAction({ action_type: 'PARAM_CHANGE', section: 'prompt', type: 'materialType', value: 'preview' });
                                                }}
                                                className={`flex-1 py-3 rounded-md text-sm font-medium transition-all flex flex-col items-center gap-1 ${params.materialType === 'preview'
                                                    ? 'bg-blue-100 text-blue-700 shadow-sm ring-1 ring-blue-200'
                                                    : 'text-neutral-text-secondary hover:bg-gray-50'
                                                    }`}
                                            >
                                                <FaBookOpenReader size={18} />
                                                課前預習
                                            </button>
                                            <button
                                                onClick={() => {
                                                    setParams({ ...params, materialType: 'review' });
                                                    logAction({ action_type: 'PARAM_CHANGE', section: 'prompt', type: 'materialType', value: 'review' });
                                                }}
                                                className={`flex-1 py-3 rounded-md text-sm font-medium transition-all flex flex-col items-center gap-1 ${params.materialType === 'review'
                                                    ? 'bg-blue-100 text-blue-700 shadow-sm ring-1 ring-blue-200'
                                                    : 'text-neutral-text-secondary hover:bg-gray-50'
                                                    }`}
                                            >
                                                <MdRateReview size={20} />
                                                課後複習
                                            </button>
                                        </div>
                                        <p className="mt-2 text-xs text-neutral-text-secondary ml-1 px-1">
                                            {params.materialType === 'preview' && '引導式導讀，幫助學生建立核心框架與學習動機'}
                                            {params.materialType === 'review' && '結構化複習，鞏固知識並提供自我檢測清單'}
                                        </p>
                                    </div>

                                    {/* Summary Detail Level - Only concise/standard */}
                                    <div className="pt-4">
                                        <label className="block text-sm font-semibold text-neutral-text-main mb-3">摘要詳盡程度</label>
                                        <div className="flex bg-white/50 p-1.5 rounded-lg border border-neutral-border shadow-sm">
                                            {[{ id: 'concise', label: '精簡' }, { id: 'standard', label: '標準' }].map((opt) => (
                                                <button
                                                    key={opt.id}
                                                    onClick={() => {
                                                        setParams({ ...params, summaryDetail: opt.id as any });
                                                        logAction({ action_type: 'PARAM_CHANGE', section: 'prompt', type: 'summaryDetail', value: opt.id });
                                                    }}
                                                    className={`flex-1 py-2 rounded-md text-sm font-medium transition-all ${params.summaryDetail === opt.id ? 'bg-blue-100 text-blue-700 shadow-sm ring-1 ring-blue-200' : 'text-neutral-text-secondary hover:bg-gray-50'}`}
                                                >
                                                    {opt.label}
                                                </button>
                                            ))}
                                        </div>
                                        <p className="mt-2 text-xs text-neutral-text-secondary ml-1 px-1">
                                            {params.summaryDetail === 'concise' && '僅列出核心要點，適合快速複習'}
                                            {params.summaryDetail === 'standard' && '包含重點解釋與術語定義，適合一般學習'}
                                        </p>
                                    </div>


                                </div>

                            ) : (
                                // Exam/Assignment Parameters
                                <div className="space-y-8">
                                    {/* Question Types */}
                                    <div>
                                        <label className="block text-sm font-semibold text-neutral-text-main mb-3">題型 (可選多個)</label>
                                        <div className="grid grid-cols-2 gap-3">
                                            {[
                                                { name: '選擇題', icon: <FaListUl size={16} /> },
                                                { name: '簡答題', icon: <FaKeyboard size={16} /> },
                                                { name: '是非題', icon: <FaCheckSquare size={16} /> },
                                                { name: '填空題', icon: <FaPenAlt size={16} /> }
                                            ].map((qType) => {
                                                const isLocked = guidedState?.preSelectedType === 'short_answer';
                                                const isSelected = params.questionTypes.includes(qType.name);

                                                return (
                                                    <button
                                                        key={qType.name}
                                                        disabled={isLocked && qType.name !== '簡答題'}
                                                        onClick={() => {
                                                            if (isLocked) return;
                                                            const newTypes = isSelected
                                                                ? params.questionTypes.filter(t => t !== qType.name)
                                                                : [...params.questionTypes, qType.name];
                                                            setParams({ ...params, questionTypes: newTypes });
                                                            logAction({ action_type: 'PARAM_CHANGE', section: 'prompt', type: 'questionTypes', value: newTypes });
                                                        }}
                                                        className={`px-3 py-3 rounded-lg text-sm font-medium border transition-all flex items-center justify-center gap-2 ${isSelected ? 'bg-blue-100 text-blue-700 border-blue-600 shadow-sm ring-1 ring-blue-200' : 'bg-white text-neutral-text-secondary border-neutral-border hover:bg-blue-50 hover:border-blue-200'} ${isLocked && qType.name !== '簡答題' ? 'opacity-40 cursor-not-allowed' : ''}`}
                                                        title={isLocked && qType.name !== '簡答題' ? '此流程鎖定為簡答題生成' : ''}
                                                    >
                                                        {qType.icon}
                                                        {qType.name}
                                                        {isLocked && qType.name === '簡答題' && <FaCheck className="ml-1 text-blue-500" size={10} />}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>

                                    {/* Question Count */}
                                    <div>
                                        <div className="flex justify-between items-center mb-2">
                                            <label className="text-sm font-semibold text-neutral-text-main">題目數量</label>
                                            <span className="text-sm font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded">{params.questionCount} 題</span>
                                        </div>
                                        <input
                                            type="range"
                                            min="1" max="20" step="1"
                                            value={params.questionCount}
                                            onChange={(e) => setParams({ ...params, questionCount: parseInt(e.target.value) })}
                                            onMouseUp={(e) => {
                                                logAction({ action_type: 'PARAM_CHANGE', section: 'prompt', type: 'questionCount', value: (e.target as HTMLInputElement).value });
                                            }}
                                            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                                        />
                                        <div className="flex justify-between text-xs text-neutral-text-secondary mt-1 px-1"><span>1</span><span>10</span><span>20</span></div>
                                    </div>
                                </div>
                            )}

                            {/* Experiment Mode Selection (Replaces AI Model) */}
                            <div className="pt-4 border-t border-gray-100 mt-6">
                                <label className="block text-sm font-semibold text-neutral-text-main mb-3">實驗模式 (Experiment Mode)</label>
                                <select
                                    value={params.ablationGroup || ''}
                                    onChange={(e) => {
                                        setParams({ ...params, ablationGroup: e.target.value as any });
                                        logAction({ action_type: 'PARAM_CHANGE', section: 'prompt', type: 'ablationGroup', value: e.target.value });
                                    }}
                                    className="w-full px-3 py-2 rounded-lg border border-neutral-border bg-white text-sm text-neutral-text-main shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-300 bg-red-50 text-red-900 border-red-200"
                                >
                                    <option value="">Production (預設完全體)</option>
                                    <option value="naive-rag">Group A: Naive RAG (無 BM25, 無 KP 定錨)</option>
                                    <option value="hybrid-rag">Group B: Hybrid RAG (無 KP 定錨)</option>
                                    <option value="kp-hybrid-rag">Group C: KP-Enhanced Hybrid RAG (同預設)</option>
                                </select>
                                <p className="mt-2 text-xs text-neutral-text-secondary ml-1 px-1">
                                    {!params.ablationGroup && '正式環境設定，功能全開'}
                                    {params.ablationGroup === 'naive-rag' && '🚫 純向量檢索，作為消融基準線'}
                                    {params.ablationGroup === 'hybrid-rag' && '🔬 加入 BM25 檢索，但不將知識點作為生成限制'}
                                    {params.ablationGroup === 'kp-hybrid-rag' && '✅ 完整混合檢索與知識點定錨 (針對實驗用)'}
                                </p>
                            </div>

                            {/* Prompt */}
                            <div className="mb-6 pt-4 border-t border-gray-100 mt-6">
                                <label className="block text-sm font-semibold text-neutral-text-main mb-3">生成指令</label>
                                <textarea
                                    value={params.prompt}
                                    onChange={(e) => setParams({ ...params, prompt: e.target.value })}
                                    onFocus={() => promptTimer.start()}
                                    onBlur={(e) => {
                                        const duration = promptTimer.stop();
                                        const val = e.target.value;
                                        if (val !== lastLoggedPromptRef.current || duration > 1) {
                                            logAction({ action_type: 'PROMPT_EDIT', section: 'prompt', finalPrompt: val }, duration > 0.1 ? duration : undefined);
                                            lastLoggedPromptRef.current = val;
                                        }
                                    }}
                                    className="w-full px-4 py-3 border border-neutral-border rounded-lg focus:ring-2 focus:ring-theme-ring text-sm leading-relaxed h-32 resize-none"
                                    placeholder={params.prompt ? "" : `請輸入您的額外要求... (例：${typeConfig[contentType === 'exam' ? 'exam' : 'material'].placeholder})`}
                                />
                                <p className="mt-2 text-xs text-neutral-text-secondary">💡 系統已自動帶入題數與題型，此處請輸入您的「教學要求」。</p>
                            </div>
                        </div>
                    </div>

                    {/* Center Column - Material Selection & Preview */}
                    <div className="col-span-6 flex items-start sticky top-4 h-[calc(100vh-6.5rem)]">
                        <div className="flex-1 rounded-xl border border-neutral-border overflow-hidden flex flex-col h-full shadow-sm z-10 relative bg-white/50 backdrop-blur-md">
                            <div
                                onClick={() => setShowMaterialModal(true)}
                                role="button"
                                aria-label="選擇參考資料"
                                tabIndex={0}
                                onKeyDown={(e) => e.key === 'Enter' && setShowMaterialModal(true)}
                                className="px-5 py-3 border-b border-neutral-border hover:brightness-95 transition-all text-left shrink-0 bg-gradient-to-r from-blue-50 to-slate-50 cursor-pointer"
                            >
                                <div className="flex items-center justify-between w-full">
                                    <h2 className="text-lg font-bold text-blue-800 flex items-center gap-2">
                                        <span className="w-8 h-8 bg-blue-100 text-blue-600 rounded-lg flex items-center justify-center font-bold">2</span>
                                        選擇參考資料
                                    </h2>
                                    <div className="flex items-center gap-2">
                                        {/* Download/View Button - Only show when a specific file is active */}
                                        {previewData && activePreviewKey?.startsWith('uploaded') && !previewData.structured_content && (
                                            previewData.download_url?.startsWith('http') ? (
                                                <a
                                                    href={previewData.download_url}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    onClick={(e) => e.stopPropagation()}
                                                    className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                                                    title="瀏覽原始網頁"
                                                >
                                                    <FaGlobe size={16} />
                                                </a>
                                            ) : (
                                                <a
                                                    href={`${API_BASE_URL}${previewData.download_url}`}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    onClick={(e) => e.stopPropagation()}
                                                    className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                                                    title="下載原始檔案"
                                                >
                                                    <FaFileDownload size={16} />
                                                </a>
                                            )
                                        )}

                                        {/* PDF Toggle Button */}
                                        {previewData && activePreviewKey?.startsWith('uploaded') && previewData.file_name?.toLowerCase().endsWith('.pdf') && (
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setShowFilePreview(!showFilePreview);
                                                }}
                                                className={`p-1.5 rounded-lg transition-colors ${showFilePreview
                                                    ? 'bg-blue-50 text-blue-600'
                                                    : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
                                                    }`}
                                                title={showFilePreview ? '顯示文字解析' : '預覽原始文件'}
                                            >
                                                {showFilePreview ? <FaCode size={16} /> : <FaEye size={16} />}
                                            </button>
                                        )}

                                        <span className="text-sm text-blue-600 font-semibold bg-white/70 px-3 py-1 rounded-full hover:bg-blue-50 transition-colors ml-2">
                                            {selectedSourceKeys.size > 0 ? `已選擇：${selectedSourceKeys.size} 個` : '＋ 新增資料'}
                                        </span>
                                    </div>
                                </div>
                            </div>



                            {/* Main Content Area with Vertical Tabs */}
                            <div className="flex-1 flex overflow-hidden">
                                {/* Preview Content */}
                                <div className="flex-1 overflow-y-auto px-4 py-3 scroll-smooth">
                                    {/* File Name Header */}
                                    {previewData && (
                                        <div className="mb-4 text-center">
                                            <h3 className="font-bold text-gray-800 text-lg truncate" title={previewData.file_name}>
                                                {previewData.file_name}
                                            </h3>
                                        </div>
                                    )}

                                    {previewLoading ? (
                                        <div className="flex items-center justify-center h-full">
                                            <div className="text-center">
                                                <div className="animate-spin h-8 w-8 border-3 border-theme-primary border-t-transparent rounded-full mx-auto mb-3" />
                                                <p className="text-sm text-neutral-text-secondary">載入預覽中...</p>
                                            </div>
                                        </div>
                                    ) : previewData ? (
                                        <div className="h-full">
                                            {/* Action Bar / Info (Simplified, no big title) */}
                                            {/* Action Bar / Info (Simplified, no big title) */}
                                            <div className="hidden items-center justify-between mb-6 px-2">
                                                <div className="flex items-center gap-2 max-w-[60%] flex-1">
                                                    {isEditingPreview ? (
                                                        <div className="flex items-center gap-1 w-full">
                                                            <input
                                                                type="text"
                                                                value={editingPreviewName}
                                                                onChange={(e) => setEditingPreviewName(e.target.value)}
                                                                onKeyDown={(e) => {
                                                                    if (e.key === 'Enter') handlePreviewRenameSubmit();
                                                                    else if (e.key === 'Escape') handlePreviewRenameCancel();
                                                                }}
                                                                autoFocus
                                                                className="flex-1 text-lg font-semibold border border-theme-primary rounded px-2 py-0.5 focus:outline-none focus:ring-1 focus:ring-theme-primary min-w-0"
                                                            />
                                                            <button
                                                                onClick={handlePreviewRenameSubmit}
                                                                className="p-1 text-green-600 hover:bg-green-50 rounded bg-white border border-gray-200 shadow-sm shrink-0"
                                                            >
                                                                <FaCheck size={14} />
                                                            </button>
                                                            <button
                                                                onClick={handlePreviewRenameCancel}
                                                                className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded bg-white border border-gray-200 shadow-sm shrink-0"
                                                            >
                                                                <FaTimes size={14} />
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <div className="flex items-center gap-2 w-full group">
                                                            <h3 className="font-semibold text-lg text-neutral-text-main truncate" title={previewData.file_name}>
                                                                {previewData.file_name}
                                                            </h3>
                                                            {activePreviewKey?.startsWith('uploaded') && (
                                                                <button
                                                                    onClick={handlePreviewRenameClick}
                                                                    className="p-1.5 text-gray-400 hover:text-theme-primary hover:bg-gray-100 rounded-full transition-all"
                                                                    title="重新命名"
                                                                >
                                                                    <FaPen size={12} />
                                                                </button>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>

                                                <div className="flex items-center gap-2">
                                                    {/* PDF Toggle Button */}
                                                    {activePreviewKey?.startsWith('uploaded') && previewData.file_name?.toLowerCase().endsWith('.pdf') && (
                                                        <button
                                                            onClick={() => setShowFilePreview(!showFilePreview)}
                                                            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors border ${showFilePreview
                                                                ? 'bg-theme-primary text-white border-theme-primary'
                                                                : 'text-neutral-text-secondary border-neutral-border hover:bg-gray-50'
                                                                }`}
                                                        >
                                                            {showFilePreview ? <FaClipboardList size={12} /> : <FaEye size={12} />}
                                                            {showFilePreview ? '顯示文字解析' : '預覽原始文件'}
                                                        </button>
                                                    )}

                                                    {previewData.structured_content ? (
                                                        <span className="text-xs text-neutral-text-tertiary bg-gray-100 px-2 py-1 rounded">AI 生成預覽</span>
                                                    ) : (
                                                        activePreviewKey?.startsWith('uploaded') && (
                                                            previewData.download_url?.startsWith('http') ? (
                                                                <button
                                                                    onClick={() => previewData.download_url && window.open(previewData.download_url, '_blank')}
                                                                    className="flex items-center gap-2 px-4 py-2 text-xs font-medium text-theme-primary bg-theme-primary-light/20 hover:bg-theme-primary-light/40 rounded-lg transition-colors cursor-pointer"
                                                                >
                                                                    <FaGlobe size={14} />
                                                                    瀏覽原始網頁
                                                                </button>
                                                            ) : (
                                                                <button
                                                                    onClick={() => previewData.download_url && window.open(`${API_BASE_URL}${previewData.download_url}`, '_blank')}
                                                                    className="flex items-center gap-2 px-4 py-2 text-xs font-medium text-theme-primary bg-theme-primary-light/20 hover:bg-theme-primary-light/40 rounded-lg transition-colors cursor-pointer"
                                                                >
                                                                    <FaFileDownload size={14} />
                                                                    下載原始檔案
                                                                </button>
                                                            )
                                                        )
                                                    )}
                                                </div>
                                            </div>

                                            {showFilePreview && previewData.download_url ? (
                                                <div className="h-full bg-gray-200 rounded-lg overflow-hidden border border-neutral-border">
                                                    <iframe
                                                        src={`${API_BASE_URL}${previewData.download_url}?inline=true`}
                                                        className="w-full h-full"
                                                        title="PDF Preview"
                                                    />
                                                </div>
                                            ) : previewData.structured_content ? (
                                                <div className="prose prose-sm max-w-none">
                                                    <ContentRenderer content={previewData.structured_content} />
                                                </div>) : previewData.pages?.length ? (
                                                    // Render Uploaded Pages
                                                    <div className="space-y-8">
                                                        {previewData.pages.map((page) => (
                                                            <div key={page.page_number} className="pb-8 last:pb-0 relative">
                                                                {/* Enhanced Page Separator - Hidden for Page 1 */}
                                                                {page.page_number > 1 && (
                                                                    <div className="flex items-center gap-4 mb-6">
                                                                        <div className="h-px bg-gray-200 flex-1"></div>
                                                                        <span className="text-xs font-bold text-gray-400 uppercase tracking-wider bg-gray-50 px-3 py-1 rounded-full border border-gray-100 shadow-sm">
                                                                            Page {page.page_number}
                                                                        </span>
                                                                        <div className="h-px bg-gray-200 flex-1"></div>
                                                                    </div>
                                                                )}

                                                                <div className="flex items-center justify-between mb-4">
                                                                    <div /> {/* Spacer for flex alignment if needed, or remove */}
                                                                    {page.has_images && (
                                                                        <span className="flex items-center gap-1 text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded-full">
                                                                            <FaFileImage size={10} /> 包含圖片
                                                                        </span>
                                                                    )}
                                                                </div>

                                                                {(() => {
                                                                    const renderPageContent = () => {
                                                                        if (!page.structured_content) {
                                                                            return (
                                                                                <div className="text-sm text-neutral-text-main whitespace-pre-wrap leading-relaxed font-newsreader">
                                                                                    {renderTextContent(page.human_text)}
                                                                                </div>
                                                                            );
                                                                        }

                                                                        // Helper to merge adjacent text items
                                                                        const mergeStructuredContent = (items: any[]) => {
                                                                            const merged: any[] = [];
                                                                            let currentText = '';

                                                                            items.forEach(item => {
                                                                                if (item.type === 'text') {
                                                                                    currentText += (currentText ? '\n' : '') + (item.content || '');
                                                                                } else {
                                                                                    if (currentText) {
                                                                                        merged.push({ type: 'text', content: currentText });
                                                                                        currentText = '';
                                                                                    }
                                                                                    merged.push(item);
                                                                                }
                                                                            });

                                                                            if (currentText) {
                                                                                merged.push({ type: 'text', content: currentText });
                                                                            }

                                                                            return merged;
                                                                        };

                                                                        const mergedContent = mergeStructuredContent(page.structured_content);

                                                                        return (
                                                                            <div className="space-y-4">
                                                                                {mergedContent.map((item: any, idx: number) => {
                                                                                    if (item.type === 'text') {
                                                                                        return (
                                                                                            <div key={idx} className="mb-2">
                                                                                                {renderTextContent(item.content)}
                                                                                            </div>
                                                                                        );
                                                                                    } else if (item.type === 'image') {
                                                                                        return (
                                                                                            <div key={idx} className="my-4 border border-gray-200 rounded-lg overflow-hidden bg-gray-50">
                                                                                                {/* Image Header */}
                                                                                                <div className="px-3 py-2 bg-gray-100 border-b border-gray-200 flex items-center gap-2 text-xs font-semibold text-gray-600">
                                                                                                    <FaImage className="text-purple-500" />
                                                                                                    圖片內容
                                                                                                </div>

                                                                                                <div className="p-4 flex flex-col items-center">
                                                                                                    <img
                                                                                                        src={item.image_path ? `${API_BASE_URL}/uploads/${item.image_path}` : (item.base64?.startsWith('data:') ? item.base64 : `data:image/jpeg;base64,${item.base64}`)}
                                                                                                        alt="Parsed content"
                                                                                                        className="max-w-full max-h-96 object-contain rounded shadow-sm border border-gray-100"
                                                                                                    />
                                                                                                </div>

                                                                                                {/* VLM Description Dropdown */}
                                                                                                <details className="group border-t border-gray-200 bg-white">
                                                                                                    <summary className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors list-none select-none">
                                                                                                        <div className="flex items-center gap-2 text-xs font-bold text-purple-600">
                                                                                                            <FaRobot size={12} />
                                                                                                            AI 圖片解析說明
                                                                                                        </div>
                                                                                                        <span className="text-gray-400 group-open:rotate-180 transition-transform">
                                                                                                            <FaChevronDown size={10} />
                                                                                                        </span>
                                                                                                    </summary>
                                                                                                    <div className="px-4 py-3 bg-purple-50/30 text-xs text-gray-700 leading-relaxed border-t border-gray-100">
                                                                                                        {item.vision_description ? (
                                                                                                            <div className="prose prose-sm prose-purple max-w-none">
                                                                                                                <ReactMarkdown
                                                                                                                    remarkPlugins={[remarkGfm]}
                                                                                                                    components={{
                                                                                                                        h1: ({ node, ...props }) => <h1 className="text-sm font-bold mt-2 mb-1" {...props} />,
                                                                                                                        h2: ({ node, ...props }) => <h2 className="text-xs font-bold mt-2 mb-1" {...props} />,
                                                                                                                        p: ({ node, ...props }) => <p className="mb-1" {...props} />,
                                                                                                                        ul: ({ node, ...props }) => <ul className="list-disc list-inside mb-1 pl-1" {...props} />,
                                                                                                                        ol: ({ node, ...props }) => <ol className="list-decimal list-inside mb-1 pl-1" {...props} />,
                                                                                                                        li: ({ node, ...props }) => <li className="mb-0.5" {...props} />
                                                                                                                    }}
                                                                                                                >
                                                                                                                    {item.vision_description}
                                                                                                                </ReactMarkdown>
                                                                                                            </div>
                                                                                                        ) : (
                                                                                                            "尚無 AI 圖片解析說明"
                                                                                                        )}
                                                                                                    </div>
                                                                                                </details>
                                                                                            </div>
                                                                                        );
                                                                                    }
                                                                                    return null;
                                                                                })}
                                                                            </div>
                                                                        );
                                                                    };

                                                                    return renderPageContent();
                                                                })()}
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                // Empty State with Enhanced Design
                                                <div className="flex flex-col items-center justify-center h-full py-12 px-6 text-center animate-fadeIn relative overflow-hidden group">
                                                    {/* Subtle Background Pattern */}
                                                    <div className="absolute inset-0 opacity-30 pointer-events-none bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:16px_16px]"></div>
                                                    <div className="absolute inset-0 bg-gradient-to-br from-transparent via-transparent to-blue-50/30 pointer-events-none"></div>

                                                    <div className="mb-8 opacity-90 grid grid-cols-4 gap-6 relative z-10">
                                                        <button onClick={() => setShowMaterialModal(true)} className="p-4 bg-red-50 rounded-2xl text-red-500 shadow-sm border border-red-100 hover:scale-110 hover:-translate-y-1 transition-all duration-300 cursor-pointer">
                                                            <FaFilePdf size={32} />
                                                        </button>
                                                        <button onClick={() => setShowMaterialModal(true)} className="p-4 bg-blue-50 rounded-2xl text-blue-500 shadow-sm border border-blue-100 hover:scale-110 hover:-translate-y-1 transition-all duration-300 cursor-pointer">
                                                            <FaFileWord size={32} />
                                                        </button>
                                                        <button onClick={() => setShowMaterialModal(true)} className="p-4 bg-orange-50 rounded-2xl text-orange-500 shadow-sm border border-orange-100 hover:scale-110 hover:-translate-y-1 transition-all duration-300 cursor-pointer">
                                                            <FaFilePowerpoint size={32} />
                                                        </button>
                                                        <button onClick={() => setShowMaterialModal(true)} className="p-4 bg-teal-50 rounded-2xl text-teal-500 shadow-sm border border-teal-100 hover:scale-110 hover:-translate-y-1 transition-all duration-300 cursor-pointer">
                                                            <FaGlobe size={32} />
                                                        </button>
                                                    </div>

                                                    <h3 className="text-2xl font-bold text-neutral-text-main mb-3 relative z-10">準備好開始製作教材了嗎？</h3>
                                                    <p className="text-neutral-text-secondary mb-10 max-w-sm text-base leading-relaxed relative z-10">
                                                        選取想要參考的資料<br />CooK.ai 將自動為您解析內容
                                                    </p>

                                                    <button
                                                        onClick={() => setShowMaterialModal(true)}
                                                        className="relative z-10 btn-primary px-10 py-4 rounded-full font-bold shadow-sm hover:shadow-md hover:scale-105 active:scale-95 transition-all flex items-center gap-2 text-lg"
                                                    >
                                                        <FaPlus /> 立即選取參考資料
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        // Empty State (No File Selected)
                                        <div className="flex flex-col items-center justify-center h-full py-12 px-6 text-center animate-fadeIn relative overflow-hidden group select-none">
                                            {/* Subtle Background Pattern */}
                                            <div className="absolute inset-0 opacity-30 pointer-events-none bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] [background-size:16px_16px]"></div>
                                            <div className="absolute inset-0 bg-gradient-to-br from-transparent via-transparent to-blue-50/30 pointer-events-none"></div>

                                            <div className="mb-8 opacity-90 grid grid-cols-4 gap-6 relative z-10">
                                                <button onClick={() => setShowMaterialModal(true)} className="p-4 bg-red-50 rounded-2xl text-red-500 shadow-sm border border-red-100 hover:scale-110 hover:-translate-y-1 transition-all duration-300 cursor-pointer">
                                                    <FaFilePdf size={32} />
                                                </button>
                                                <button onClick={() => setShowMaterialModal(true)} className="p-4 bg-blue-50 rounded-2xl text-blue-500 shadow-sm border border-blue-100 hover:scale-110 hover:-translate-y-1 transition-all duration-300 cursor-pointer">
                                                    <FaFileWord size={32} />
                                                </button>
                                                <button onClick={() => setShowMaterialModal(true)} className="p-4 bg-orange-50 rounded-2xl text-orange-500 shadow-sm border border-orange-100 hover:scale-110 hover:-translate-y-1 transition-all duration-300 cursor-pointer">
                                                    <FaFilePowerpoint size={32} />
                                                </button>
                                                <button onClick={() => setShowMaterialModal(true)} className="p-4 bg-teal-50 rounded-2xl text-teal-500 shadow-sm border border-teal-100 hover:scale-110 hover:-translate-y-1 transition-all duration-300 cursor-pointer">
                                                    <FaGlobe size={32} />
                                                </button>
                                            </div>

                                            <h3 className="text-2xl font-bold text-neutral-text-main mb-3 relative z-10">準備好開始製作教材了嗎？</h3>
                                            <p className="text-neutral-text-secondary mb-10 max-w-sm text-base leading-relaxed relative z-10">
                                                點擊上方「+ 新增資料」按鈕<br />或直接點擊下方按鈕開始選擇參考資料
                                            </p>

                                            <button
                                                onClick={() => setShowMaterialModal(true)}
                                                className="relative z-10 btn-primary px-10 py-4 rounded-full font-bold shadow-sm hover:shadow-md hover:scale-105 active:scale-95 transition-all flex items-center gap-2 text-lg"
                                            >
                                                <FaPlus /> 立即選取參考資料
                                            </button>
                                        </div>
                                    )}
                                </div>


                            </div>
                        </div>

                        {/* Notebook Tabs Outside the Box */}
                        {selectedItemsList.length > 0 && (
                            <div className="w-10 flex flex-col pt-14 gap-2 shrink-0 relative z-20 -ml-[1px]">
                                {selectedItemsList.map((item) => {
                                    const isActive = activePreviewKey === item.key;

                                    return (
                                        <button
                                            key={item.key}
                                            onClick={() => setActivePreviewKey(item.key)}
                                            className={`
                                                w-10 h-28 rounded-r-lg border-y border-r flex flex-col items-center justify-start py-3 px-1 transition-all duration-200 cursor-pointer shadow-sm relative group
                                                ${isActive
                                                    ? 'bg-blue-100 text-blue-700 border-blue-200 border-l-transparent z-20 w-11 font-bold translate-x-[1px] shadow-md -ml-[1px]'
                                                    : 'bg-white text-gray-400 border-gray-200 z-10 hover:bg-blue-50 hover:text-blue-600 hover:translate-x-0.5 hover:shadow-md'
                                                }
                                            `}
                                        >
                                            <span className="[writing-mode:vertical-rl] text-xs tracking-widest truncate w-full h-full select-none text-left" style={{ textOrientation: 'upright' }}>
                                                {item.name.split('').map((char, i) => (
                                                    <span key={i} className={/[a-zA-Z0-9\.\-_]/.test(char) ? 'text-[10px]' : ''}>{char}</span>
                                                ))}
                                            </span>

                                            {/* Enhanced Tooltip */}
                                            <div className="absolute right-full mr-2 top-1/2 -translate-y-1/2 px-3 py-2 bg-gray-800 text-white text-sm font-medium rounded-md shadow-xl opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
                                                {item.name}
                                                <div className="absolute top-1/2 -translate-y-1/2 -right-1 w-2 h-2 bg-gray-800 rotate-45"></div>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    {/* Right Column = Knowledge Point Selection */}
                    <div className="col-span-3">
                        <KnowledgePointPanel
                            activePreviewKey={activePreviewKey}
                            selectedSourceKeys={selectedSourceKeys}
                            loading={loading}
                            error={error}
                            handleGenerate={handleGenerate}
                            onKPSelectionChange={handleKPSelectionChange}
                            userId={user?.user_id}
                            courseId={courseId ? parseInt(courseId) : undefined}
                            unitId={searchParams.get('unit_id') ? parseInt(searchParams.get('unit_id')!) : undefined}
                            preSelectedNames={preSelectedNames}
                            weakKPNames={weakKPNames}
                            onActionLog={(_, type, cfg, dur) => {
                                if (type === 'MAP_OPEN') {
                                    setIsKnowledgeMapOpen(true);
                                    return; // Handled by useEffect in GeneratorSettings
                                }
                                if (type === 'MAP_CLOSE') {
                                    setIsKnowledgeMapOpen(false);
                                    return; // Handled by useEffect in GeneratorSettings
                                }
                                // Ensure action_type is in cfg for unified logging
                                const finalCfg = { ...cfg, action_type: type };
                                logAction(finalCfg, dur ? dur / 1000 : undefined);
                            }}
                        />
                    </div>
                </div>
            </div>

            {/* Toast Notification */}
            {toast.show && (
                <Toast
                    key={`${toast.message}-${toast.type}`}
                    message={toast.message}
                    type={toast.type}
                    onClose={() => setToast({ ...toast, show: false })}
                />
            )}

            {/* Confirm Dialog */}
            <ConfirmDialog
                isOpen={confirmDialog.show}
                title="刪除教材"
                message="確定要刪除此教材嗎？此操作無法復原。"
                confirmText="刪除"
                cancelText="取消"
                variant="danger"
                onConfirm={confirmDeleteMaterial}
                onCancel={() => setConfirmDialog({ show: false, id: null })}
            />

            {/* Cancel Confirmation Dialog */}
            <ConfirmDialog
                isOpen={showCancelConfirm}
                title="確認取消？"
                message="您目前的設定將不會被儲存。確定要放棄並返回課程頁面嗎？"
                confirmText="放棄並返回"
                cancelText="繼續編輯"

                onConfirm={() => navigate(`/teacher/courses/${courseId}`)}
                onCancel={() => setShowCancelConfirm(false)}
            />
        </div>
    );
}
