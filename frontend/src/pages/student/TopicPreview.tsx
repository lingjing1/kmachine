import { useState, useEffect, useRef, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams, useOutletContext } from 'react-router-dom';
import {
  FaChevronRight, FaRobot, FaPaperPlane,
  FaSpinner, FaFilePdf, FaFilePowerpoint, FaFileWord, FaFileAlt, FaDownload, FaLock,
  FaCloudUploadAlt, FaCheckCircle, FaTimesCircle, FaChevronLeft, FaTrash
} from 'react-icons/fa';
import { FaLink } from 'react-icons/fa6';
import { ImCheckmark } from 'react-icons/im';

import {
  getStudentUnitContents,
  sendMessage,
  getConversations,
  getConversationMessages,
  uploadFileSubmission,
  getFileSubmissionStatus,
  deleteFileSubmissionFile,
  FileSubmissionStatus,
  StudentUnitContentsResponse,
  StudentContentItem,
  SourceItem,
  getMaterialDownloadUrl,
  submitReadingLog,
  submitReadingLogKeepalive,
  startLearningSession,
  sendSessionHeartbeat,
  EvaluationResult
} from '../../services/studentApi';

import { SummaryContentView } from '../../components/reports/SummaryContentView';
import ShortAnswerQuizSection from '../../components/student/ShortAnswerQuizSection';
import { formatDateTime, formatDateOnly } from '../../utils/dateUtils';
import { safeRandomUUID } from '../../utils/uuid';
import RecommendedQuestionsSection from '../../components/student/RecommendedQuestionsSection';
import ReviewPersonalMaterialsSection from '../../components/student/ReviewPersonalMaterialsSection';
import ReviewMasteredQuestionsSection from '../../components/student/ReviewMasteredQuestionsSection';
import MaterialRatingModal from '../../components/student/MaterialRatingModal';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Spinner from '../../components/common/Spinner';
import { PDFViewer } from '../../components/common/PDFViewer';
import Tooltip from '../../components/common/Tooltip';
import ConfirmDialog from '../../components/common/ConfirmDialog';
import Toast from '../../components/common/Toast';

interface OutletContext {
  setBreadcrumbPaths: React.Dispatch<React.SetStateAction<Array<{ name: string; path: string }> | null>>;
  breadcrumbPaths: Array<{ name: string; path: string }> | null;
}

interface ChatMessage {
  role: 'user' | 'ai';
  text: string;
  sources?: SourceItem[];
}

const TopicPreview = () => {

  const { courseId, unitId } = useParams<{ courseId: string; unitId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const context = useOutletContext<OutletContext>();
  const contentIdParam = searchParams.get('contentId');
  const stage = searchParams.get('stage') || 'preview'; // 'preview' or 'review'



  // State
  const [unitContents, setUnitContents] = useState<StudentUnitContentsResponse | null>(null);
  const [activeContent, setActiveContent] = useState<StudentContentItem | null>(null);
  const [courseName, setCourseName] = useState<string>('課程');

  const [isLoading, setIsLoading] = useState(true);
  const [isRatingModalOpen, setIsRatingModalOpen] = useState(false);
  const [sessionCompletedIds, setSessionCompletedIds] = useState<number[]>([]);
  const [shouldNavigateOnClose, setShouldNavigateOnClose] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Completion Tracking
  const [completedItemIds, setCompletedItemIds] = useState<number[]>([]);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [confirmConfig, setConfirmConfig] = useState<{
    title: string;
    message: string;
    onConfirm: () => void;
    confirmLabel?: string;
    cancelLabel?: string;
    type?: 'warning' | 'info' | 'success' | 'danger';
  } | null>(null);

  const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'error' | 'info' }>({
    show: false,
    message: '',
    type: 'success'
  });

  // Chatbot Sidebar State
  const CHAT_WELCOME_MESSAGE: ChatMessage = { role: 'ai', text: '你好！我是你的 AI 學習助手。關於這個內容有任何問題都可以問我喔！' };
  const [isChatOpen, setIsChatOpen] = useState(true);
  const [chatMessage, setChatMessage] = useState('');
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([CHAT_WELCOME_MESSAGE]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isLoadingChat, setIsLoadingChat] = useState(false);
  const [isLoadingChatHistory, setIsLoadingChatHistory] = useState(true);
  const chatHistoryRef = useRef<HTMLDivElement>(null);

  // 切換教材（activeContent）時，還原這份教材既有的對話紀錄，而不是每次都重置成歡迎詞
  useEffect(() => {
    let cancelled = false;

    const loadChatHistory = async () => {
      if (!courseId || !unitId || !activeContent?.id) return;
      setIsLoadingChatHistory(true);
      try {
        const result = await getConversations({
          courseId: parseInt(courseId),
          unitId: parseInt(unitId),
          contentId: activeContent.id,
        });

        if (cancelled) return;

        const latest = result.conversations?.[0];
        if (!latest) {
          setConversationId(null);
          setChatHistory([CHAT_WELCOME_MESSAGE]);
          return;
        }

        const history = await getConversationMessages(latest.conversation_id);
        if (cancelled) return;

        setConversationId(latest.conversation_id);
        setChatHistory(
          history.messages.map((m) => ({
            role: m.role === 'user' ? 'user' : 'ai',
            text: m.content?.message || '',
          }))
        );
      } catch (err) {
        if (!cancelled) {
          console.error('載入聊天歷史失敗：', err);
          setConversationId(null);
          setChatHistory([CHAT_WELCOME_MESSAGE]);
        }
      } finally {
        if (!cancelled) setIsLoadingChatHistory(false);
      }
    };

    loadChatHistory();

    return () => {
      cancelled = true;
    };
  }, [courseId, unitId, activeContent?.id]);

  // Sidebar Width States
  const [chatWidth, setChatWidth] = useState(400); // ~30% width
  const [citationWidth, setCitationWidth] = useState(600); // Wider default
  const [activeResizer, setActiveResizer] = useState<'chat' | 'citation' | null>(null);

  // Citation sidebar states
  const [isCitationOpen, setIsCitationOpen] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<{
    chunkId: string | number;
    evidence: string;
    matchScore?: number;
    fullChunk?: any;
  } | null>(null);

  // File upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [fileSubmission, setFileSubmission] = useState<FileSubmissionStatus | null>(null);
  const [quizScore, setQuizScore] = useState<{ score?: number, is_manual?: boolean, includeInGrade?: boolean } | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // [NEW] Reading Log State
  const [unitSessionId, setUnitSessionId] = useState<string | undefined>(undefined);
  const [activeDuration, setActiveDuration] = useState<number>(0);
  const [maxScrollDepth, setMaxScrollDepth] = useState<number>(0);
  const citationInteractionsRef = useRef<any[]>([]);
  const lastLoggedContentIdRef = useRef<number | null>(null);
  const activeCitationRef = useRef<{
    chunkId: string | number;
    startTime: number;
    sectionId?: number;
    refType?: 'question' | 'section';
  } | null>(null);

  // Handle Independent Resize Logic
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!activeResizer) return;

      e.preventDefault(); // Prevent text selection

      if (activeResizer === 'chat') {
        // Chat starts from right edge. Width = WindowWidth - MouseX
        const newWidth = window.innerWidth - e.clientX;
        // Limit width: min 300px, max 800px
        if (newWidth >= 300 && newWidth <= 800) {
          setChatWidth(newWidth);
        }
      } else if (activeResizer === 'citation') {
        // Citation is to the left of Chat (if Chat is open)
        // Its right edge is at: WindowWidth - (isChatOpen ? chatWidth : 0)
        // Its left edge is MouseX
        // So Width = RightEdge - MouseX
        const rightEdge = window.innerWidth - (isChatOpen ? chatWidth : 0);
        const newWidth = rightEdge - e.clientX;

        // Limit width: min 350px, max 900px
        if (newWidth >= 350 && newWidth <= 900) {
          setCitationWidth(newWidth);
        }
      }
    };

    const handleMouseUp = () => {
      setActiveResizer(null);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    if (activeResizer) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [activeResizer, isChatOpen, chatWidth]);

  // [NEW] Initialize Learning Session
  useEffect(() => {
    const initSession = async () => {
      if (!courseId || !unitId) return;
      try {
        const res = await startLearningSession({
          course_id: parseInt(courseId),
          unit_id: parseInt(unitId),
          context_data: { stage, entry: 'topic_preview' }
        });
        setUnitSessionId(res.session_id);
        console.log('[Session] Started student learning session:', res.session_id);
      } catch (err) {
        console.error('[Session] Failed to start learning session:', err);
        // Fallback to local UUID to allow logging even if session table fails
        setUnitSessionId(safeRandomUUID());
      }
    };
    initSession();
  }, [courseId, unitId, stage]);

  // [NEW] Session Heartbeat
  useEffect(() => {
    if (!unitSessionId) return;
    const interval = setInterval(() => {
      sendSessionHeartbeat(unitSessionId).catch(err =>
        console.warn('[Session] Heartbeat failed:', err)
      );
    }, 60000); // 1 minute
    return () => clearInterval(interval);
  }, [unitSessionId]);

  // Scroll to bottom of chat
  useEffect(() => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
    }
  }, [chatHistory, isChatOpen]);

  const handleRatingCancel = () => {
    setIsRatingModalOpen(false);
    setShouldNavigateOnClose(false);
    // If the user cancels the session-end rating, we should still clear or keep the session IDs?
    // User said "回課程時... 跳出評分介面", if they cancel they might want to return later.
    // But usually once they return to course, the session is over.
    // Let's clear them on successful submit. If they cancel, we'll keep them in case they come back?
    // Actually, "回到課程" is the trigger. If they cancel, they are still on the preview page.
  };

  const handleReturnClick = () => {
    const currentIsCompleted = completedItemIds.includes(activeContent?.id || -1);

    // Check if current practice is enabled but not completed
    if (isPracticeEnabled && !currentIsCompleted) {
      setConfirmConfig({
        title: '尚未完成練習',
        message: '您還沒有完成這份教材的練習題，閱讀進度將遺失，確定要返回課程嗎?',
        type: 'warning',
        onConfirm: () => {
          setShowConfirmDialog(false);
          proceedWithReturn();
        }
      });
      setShowConfirmDialog(true);
      return;
    }

    proceedWithReturn();
  };

  const proceedWithReturn = () => {
    if (sessionCompletedIds.length > 0) {
      setIsRatingModalOpen(true);
      setShouldNavigateOnClose(true);
    } else {
      navigate(`/student/course/${courseId}`);
    }
  };

  const isItemPracticeEnabled = (item: StudentContentItem) => {
    const isAttachment = item.content_subtype === 'attachment';
    const isUploaded = item.source_type === 'uploaded_content';
    // Only count items that are materials, not attachments, not uploaded,
    // AND actually have practice questions in question_bank for their KPs
    const hasPractice = item.has_practice_questions !== false; // default true if undefined
    return item.content_type === 'material' && !isAttachment && !isUploaded && hasPractice;
  };

  const handleCompleteUnitClick = () => {
    if (!unitContents) return;

    // In review stage, practice is unit-level (ReviewPersonalMaterialsSection +
    // ReviewMasteredQuestionsSection), not per-content, so skip per-content completion check.
    if (stage === 'review') {
      proceedWithReturn();
      return;
    }

    // Filter only materials that actually have practice
    const materialsWithPractice = unitContents.items.filter(isItemPracticeEnabled);

    // If no materials have practice, just proceed with return/rating logic
    if (materialsWithPractice.length === 0) {
      proceedWithReturn();
      return;
    }

    const missingItems = materialsWithPractice.filter(item => !completedItemIds.includes(item.id));

    if (missingItems.length === 0) {
      // All items with practice are completed
      if (sessionCompletedIds.length > 0) {
        setIsRatingModalOpen(true);
        setShouldNavigateOnClose(true);
      } else {
        navigate(`/student/course/${courseId}`);
      }
    } else if (missingItems.length < materialsWithPractice.length) {
      // At least one completed, but some missing
      const missingTitles = missingItems.map((item, idx) => `${idx + 1}. ${item.title}`).join('\n');
      setConfirmConfig({
        title: '部分練習尚未完成',
        message: `您還有以下教材的練習題尚未完成：\n\n${missingTitles}\n\n確定要返回課程列表嗎？`,
        type: 'info',
        confirmLabel: '確定返回',
        cancelLabel: '繼續練習',
        onConfirm: () => {
          setShowConfirmDialog(false);
          if (sessionCompletedIds.length > 0) {
            setIsRatingModalOpen(true);
            setShouldNavigateOnClose(true);
          } else {
            navigate(`/student/course/${courseId}`);
          }
        }
      });
      setShowConfirmDialog(true);
    } else {
      // None of the items with practice are completed
      setConfirmConfig({
        title: '尚未開始練習',
        message: '您還沒有完成任何一份教材的練習題，請先完成練習後再送出。',
        type: 'warning',
        confirmLabel: '我知道了',
        cancelLabel: '取消',
        onConfirm: () => setShowConfirmDialog(false)
      });
      setShowConfirmDialog(true);
    }
  };

  const handlePracticeComplete = (itemId: number) => {
    // Check if the item was already completed before this practice session
    const wasAlreadyCompleted = completedItemIds.includes(itemId);

    setCompletedItemIds(prev => prev.includes(itemId) ? prev : [...prev, itemId]);

    // Also update is_preview_completed in unitContents and activeContent so that
    // the download-lock UI and sidebar immediately reflect completion without a refetch.
    setUnitContents(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map(item =>
          item.id === itemId ? { ...item, is_preview_completed: true } : item
        )
      };
    });
    setActiveContent(prev => {
      if (!prev || prev.id !== itemId) return prev;
      return { ...prev, is_preview_completed: true };
    });

    // Only trigger rating session if it's a NEW completion
    if (!wasAlreadyCompleted) {
      setSessionCompletedIds(prev => prev.includes(itemId) ? prev : [...prev, itemId]);
    }
  };

  const handleRatingSubmitSuccess = () => {
    if (shouldNavigateOnClose) {
      navigate(`/student/course/${courseId}`);
    }
    setIsRatingModalOpen(false);
    setShouldNavigateOnClose(false);
    setSessionCompletedIds([]); // Clear session IDs after successful batch rating
  };



  // Fetch unit data from API
  useEffect(() => {
    const fetchUnitContents = async () => {
      if (!unitId) return;

      setIsLoading(true);
      setError(null);

      try {
        console.log(`Fetching contents for unit ${unitId}...`);
        const data = await getStudentUnitContents(parseInt(unitId));
        setUnitContents(data);

        // Determine active content
        if (data.items.length > 0) {
          let targetItem = data.items[0];
          if (contentIdParam) {
            const found = data.items.find(i => i.id === parseInt(contentIdParam));
            if (found) targetItem = found;
          }
          setActiveContent(targetItem);
        }
      } catch (err) {
        console.error('Error fetching unit contents:', err);
        setError('無法載入單元內容，請稍後再試。');
      } finally {
        setIsLoading(false);
      }
    };

    fetchUnitContents();
  }, [unitId]);

  // Fetch course name
  useEffect(() => {
    const fetchCourseName = async () => {
      try {
        const { getEnrolledCourses } = await import('../../services/studentApi');
        const courses = await getEnrolledCourses();
        const course = courses.find((c: any) => c.id === parseInt(courseId!));
        if (course) {
          setCourseName(course.name);
        }
      } catch (err) {
        console.error('Failed to fetch course name:', err);
      }
    };
    if (courseId) {
      fetchCourseName();
    }
  }, [courseId]);

  // Set breadcrumb in Header
  useEffect(() => {
    if (context?.setBreadcrumbPaths && activeContent) {
      // 根據 content_type 決定最後一層麵包屑名稱
      const contentLabel = activeContent.content_type === 'material' ? '閱讀教材' : '閱讀試卷';

      context.setBreadcrumbPaths([
        { name: '我的課程', path: '/student' },
        { name: courseName, path: `/student/course/${courseId}` },
        { name: contentLabel, path: window.location.pathname + window.location.search }
      ]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, courseName, activeContent?.content_type]); // Update when course name or content type changes

  // Update active content when contentId param changes
  useEffect(() => {
    if (unitContents && contentIdParam) {
      const found = unitContents.items.find(i => i.id === parseInt(contentIdParam));
      if (found) {
        setActiveContent(found);
      }
    }
  }, [contentIdParam, unitContents]);

  // Handle auto-scroll to top when content or tab changes
  useEffect(() => {
    if (unitContents?.items) {
      const existing = unitContents.items
        .filter(item => item.is_preview_completed)
        .map(item => item.id);
      setCompletedItemIds(existing);
    }
  }, [unitContents]);

  // Handle auto-scroll to top when content changes
  useEffect(() => {
    const scrollContainer = document.querySelector('.custom-scrollbar');
    if (scrollContainer) {
      scrollContainer.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, [activeContent?.id]);

  // Memoize knowledge point IDs to prevent re-renders of RecommendedQuestionsSection
  // Use a stable JSON string as dependency key so reference changes to the array don't trigger re-computation
  const kpIdKey = activeContent?.knowledge_points?.map(kp => kp.id).join(',') ?? '';
  const knowledgePointIds = useMemo(() => {
    return activeContent?.knowledge_points?.map(kp => kp.id) || [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kpIdKey]);

  useEffect(() => {
    if (activeContent?.assignment_type === 'file_upload') {
      getFileSubmissionStatus(activeContent.id)
        .then(status => setFileSubmission(status))
        .catch(err => console.error('Failed to fetch file submission status:', err));
      setQuizScore(null);
    } else {
      setFileSubmission(null);
      setSelectedFile(null);
      setQuizScore(null);
    }
  }, [activeContent?.id, activeContent?.assignment_type]);

  // Navigation Logic
  const filteredItems = useMemo(() => {
    if (!unitContents) return [];
    return unitContents.items.filter(item => {
      // Logic synced with Course.tsx (Student view)
      const isAttachment = item.content_subtype === 'attachment';

      // Filter out attachments from the TopicPreview navigation flow
      if (isAttachment) return false;

      if (stage === 'preview') {
        return item.content_subtype === 'preview' || !item.content_subtype;
      } else {
        // review stage
        return item.content_subtype === 'review' || !item.content_subtype || item.content_subtype === 'exercise';
      }
    });
  }, [unitContents, stage]);

  const { prevItem, nextItem, itemIndex, totalItems } = useMemo(() => {
    if (!filteredItems.length || !activeContent) return { prevItem: null, nextItem: null, itemIndex: 0, totalItems: 0 };
    const currentIndex = filteredItems.findIndex(i => i.id === activeContent.id);
    return {
      prevItem: currentIndex > 0 ? filteredItems[currentIndex - 1] : null,
      nextItem: currentIndex !== -1 && currentIndex < filteredItems.length - 1 ? filteredItems[currentIndex + 1] : null,
      itemIndex: currentIndex !== -1 ? currentIndex + 1 : 0,
      totalItems: filteredItems.length
    };
  }, [filteredItems, activeContent]);

  const handleNavigateToItem = (item: StudentContentItem) => {
    const isAttachment = item.content_subtype === 'attachment';
    const targetUrl = isAttachment
      ? `/student/course/${courseId}/units/${unitId}/attachment/${Math.abs(item.id)}`
      : `/student/course/${courseId}/units/${unitId}/preview?contentId=${item.id}${stage === 'review' ? '&stage=review' : ''}`;

    // Find index for state
    const targetIndex = filteredItems.findIndex(i => i.id === item.id);

    navigate(targetUrl, {
      state: {
        itemIndex: targetIndex !== -1 ? targetIndex + 1 : null,
        totalItems: filteredItems.length
      }
    });
  };

  // Handle Chat Message
  const handleSendMessage = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!chatMessage.trim() || isLoadingChat) return;

    const userMsg = chatMessage;
    setChatMessage('');
    setChatHistory(prev => [...prev, { role: 'user', text: userMsg }]);
    setIsLoadingChat(true);

    try {
      // Send message using request object format
      const response = await sendMessage({
        message: userMsg,
        conversation_id: conversationId || undefined,
        course_id: parseInt(courseId!),
        unit_id: parseInt(unitId!),
        content_id: activeContent?.id,
        unit_session_id: unitSessionId,
      });

      setChatHistory(prev => [...prev, {
        role: 'ai',
        text: response.assistant_response,
        sources: response.sources
      }]);

      if (response.conversation_id) {
        setConversationId(response.conversation_id);
      }
    } catch (err) {
      console.error('Chat error:', err);
      setChatHistory(prev => [...prev, { role: 'ai', text: '抱歉，我目前無法回答，請稍後再試。' }]);
    } finally {
      setIsLoadingChat(false);
    }
  };

  // [NEW] Log Reading Behavior
  const logReadingBehavior = async (exitAction?: string, useKeepalive: boolean = false) => {
    if (!activeContent || activeContent.content_type !== 'material' || !unitSessionId) return;

    // Flush final citation if still open
    flushCitationInteraction();

    const duration = activeDuration;
    if (duration === 0 && useKeepalive) return; // Prevent empty logs on StrictMode unmounts

    const logData = {
      unit_session_id: unitSessionId,
      content_id: activeContent.id,
      unit_id: parseInt(unitId!),
      stay_duration_seconds: duration,
      max_scroll_depth: Math.round(maxScrollDepth * 100) / 100,
      citation_interactions: citationInteractionsRef.current,
      exit_action: exitAction
    };

    try {
      if (useKeepalive) {
        submitReadingLogKeepalive(logData); // Don't await keepalive
      } else {
        await submitReadingLog(logData);
      }
      console.log(`[Log] Submitted reading log for content ${activeContent.id}, duration: ${duration}s, exit: ${exitAction}`);
    } catch (err) {
      console.error('[Log] Failed to submit reading log:', err);
    }
  };

  // Keep a ref to the latest logging function for unmount/unload handlers
  const logReadingBehaviorRef = useRef(logReadingBehavior);
  useEffect(() => {
    logReadingBehaviorRef.current = logReadingBehavior;
  });

  // Scroll Tracking Effect
  useEffect(() => {
    const scrollContainer = document.querySelector('.custom-scrollbar') || window;

    const handleScroll = () => {
      let currentScroll = 0;
      let totalScroll = 0;

      if (scrollContainer === window) {
        currentScroll = window.scrollY + window.innerHeight;
        totalScroll = document.documentElement.scrollHeight;
      } else {
        const el = scrollContainer as HTMLElement;
        currentScroll = el.scrollTop + el.clientHeight;
        totalScroll = el.scrollHeight;
      }

      const depth = totalScroll > 0 ? currentScroll / totalScroll : 0;
      if (depth > maxScrollDepth) {
        setMaxScrollDepth(depth);
      }
    };

    scrollContainer.addEventListener('scroll', handleScroll, { passive: true });
    return () => scrollContainer.removeEventListener('scroll', handleScroll);
  }, [maxScrollDepth]);

  // Handle Content Change Logging
  useEffect(() => {
    // When activeContent changes, log the PREVIOUS one before starting new tracker
    if (lastLoggedContentIdRef.current !== null && activeContent && lastLoggedContentIdRef.current !== activeContent.id) {
      logReadingBehavior('next_item');
    }

    // Reset trackers for current content
    setActiveDuration(0);
    setMaxScrollDepth(0);
    citationInteractionsRef.current = [];
    lastLoggedContentIdRef.current = activeContent?.id || null;
  }, [activeContent?.id]);

  // Active Time Tracking Interval
  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden && activeContent?.content_type === 'material') {
        setActiveDuration(prev => prev + 1);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [activeContent?.id]);



  // Handle Unmount Logging
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (lastLoggedContentIdRef.current !== null) {
        logReadingBehaviorRef.current('browser_close', true);
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      if (lastLoggedContentIdRef.current !== null) {
        logReadingBehaviorRef.current('back_to_course', true);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // [NEW] Flush Citation Interaction
  const flushCitationInteraction = () => {
    if (activeCitationRef.current) {
      const now = Date.now();
      const duration = Math.round((now - activeCitationRef.current.startTime) / 1000);
      const entry = {
        chunk_id: activeCitationRef.current.chunkId,
        section_id: activeCitationRef.current.sectionId,
        ref_type: activeCitationRef.current.refType,
        timestamp: new Date(activeCitationRef.current.startTime).toISOString(),
        stay_duration_seconds: duration,
        action: 'view'
      };
      citationInteractionsRef.current.push(entry);
      activeCitationRef.current = null;
    }
  };

  // Handle citation click
  const handleCitationClick = (
    chunkId: number | string,
    evidence: string,
    matchScore?: number,
    fullChunk?: any,
    sectionId?: number,
    refType?: 'question' | 'section'
  ) => {
    // Flush previous citation if exists
    flushCitationInteraction();

    setSelectedCitation({ chunkId, evidence, matchScore, fullChunk });
    setIsCitationOpen(true);

    // Start new citation timer
    activeCitationRef.current = {
      chunkId,
      startTime: Date.now(),
      sectionId,
      refType
    };

    // Log the click itself too if desired, but user specifically asked for stay duration
    // usually "view" duration covers the click intent.
  };

  // When citation sidebar is closed manually
  const closeCitationSidebar = () => {
    flushCitationInteraction();
    setIsCitationOpen(false);
  };


  // Dynamic Sidebar Height Logic
  const [sidebarHeight, setSidebarHeight] = useState<number | string>('calc(100vh - 120px)');
  const lastHeightRef = useRef<number>(0);

  useEffect(() => {
    const calculateHeight = () => {
      const footer = document.getElementById('app-footer');
      const row = document.getElementById('main-layout-row');

      if (!row) return;

      const viewportHeight = window.innerHeight;
      const footerRect = footer?.getBoundingClientRect();
      const rowRect = row.getBoundingClientRect();

      // Sidebars are sticky top-6, so they start 24px from viewport top or at row top
      const topGap = Math.max(24, rowRect.top + 24);

      let bottomGap = 24; // Default margin
      if (footerRect && footerRect.top < viewportHeight) {
        // The visible height of the footer + margin
        bottomGap = Math.max(24, (viewportHeight - footerRect.top) + 24);
      }

      const newHeight = Math.max(300, viewportHeight - topGap - bottomGap);

      // Threshold check to prevent micro-oscillations/flickering
      if (Math.abs(newHeight - lastHeightRef.current) > 2) {
        lastHeightRef.current = newHeight;
        setSidebarHeight(newHeight);
      }
    };

    // Find the actual scroll container - in Student.tsx it's the parent with .custom-scrollbar
    // We search upwards from the row to find the nearest scrollable parent
    const row = document.getElementById('main-layout-row');
    const scrollContainer = row?.closest('.overflow-y-auto') || window;

    scrollContainer.addEventListener('scroll', calculateHeight, { passive: true });
    window.addEventListener('resize', calculateHeight);

    // Initial calculation
    calculateHeight();

    return () => {
      scrollContainer.removeEventListener('scroll', calculateHeight);
      window.removeEventListener('resize', calculateHeight);
    };
  }, []);

  // Helper for Subtype Labels (Synced with teacher view)
  const getSubtypeLabel = (type: string, subtype?: string | null) => {
    if (!subtype) {
      if (type === 'material') return '教材';
      if (type === 'assignment' || type === 'exam') return '試卷';
      return '內容';
    }

    const map: Record<string, string> = {
      'preview': '預習教材',
      'review': '複習教材',
      'quiz': '小考',
      'homework': '作業',
      'midterm': '期中考',
      'final': '期末考'
    };

    return map[subtype] || subtype;
  };

  // Helper to determine icon for file type
  const getFileIcon = (filename: string) => {
    const lower = filename.toLowerCase();
    if (lower.endsWith('.pdf')) return FaFilePdf;
    if (lower.endsWith('.ppt') || lower.endsWith('.pptx')) return FaFilePowerpoint;
    if (lower.endsWith('.doc') || lower.endsWith('.docx')) return FaFileWord;
    return FaFileAlt;
  };

  // 解析教材內容與練習題、小考題目
  const parsedContent = useMemo(() => {
    if (!activeContent?.content) return null;
    try {
      let content = typeof activeContent.content === 'string'
        ? JSON.parse(activeContent.content)
        : activeContent.content;

      if (activeContent?.content_type === 'material') {
        if (content?.content && typeof content.content === 'object' && !Array.isArray(content.content)) {
          if (content.content.type === 'summary_report' || content.content.type === 'summary' || content.content.content) {
            content = content.content;
          }
        }
      }
      return content;
    } catch (e) {
      console.error("Parse content error:", e);
      return activeContent.content;
    }
  }, [activeContent]);

  const isPracticeEnabled = useMemo(() => {
    return activeContent?.content_type === 'material' &&
      activeContent?.source_type !== 'uploaded_content' &&
      stage !== 'review' &&
      !activeContent?.is_expired &&
      parsedContent?.recommendation_config?.enabled !== false;
  }, [activeContent, stage, parsedContent]);

  // 強健的題目提取邏輯 (相容各種 JSON 結構)
  const extractedQuestions = useMemo(() => {
    if (!parsedContent) return [];

    let questionsArr: any[] = [];

    if (Array.isArray(parsedContent)) {
      questionsArr = parsedContent;
    } else if (parsedContent.questions && Array.isArray(parsedContent.questions)) {
      questionsArr = parsedContent.questions;
    } else if (parsedContent.content && Array.isArray(parsedContent.content)) {
      questionsArr = parsedContent.content;
    } else if (parsedContent.content && parsedContent.content.questions && Array.isArray(parsedContent.content.questions)) {
      questionsArr = parsedContent.content.questions;
    } else if (parsedContent.content && parsedContent.content.content && Array.isArray(parsedContent.content.content)) {
      questionsArr = parsedContent.content.content;
    } else if (typeof parsedContent === 'object') {
      // 嘗試找尋任何數組類型的欄位
      const arrayField = Object.values(parsedContent).find(val => Array.isArray(val)) as any[];
      if (arrayField) questionsArr = arrayField;
    }

    // 過濾掉非題目類型的區塊 (如 section_header)
    return questionsArr.filter(q => q && (q.question_text || q.question || q.stem || q.type === 'multiple_choice' || q.type === 'short_answer' || q.type === 'true_false' || q.type === 'fill_in_blank'));
  }, [parsedContent]);

  // 計算截止時間（file_upload 用）
  const isPastDeadline = useMemo(() => {
    if (activeContent?.is_expired) return true;
    return activeContent?.end_time
      ? new Date() > new Date(activeContent.end_time)
      : false;
  }, [activeContent?.end_time, activeContent?.is_expired]);

  if (isLoading) {
    return <div className="h-screen flex justify-center items-center"><Spinner /></div>;
  }

  if (error) {
    return (
      <div className="h-screen flex flex-col justify-center items-center gap-4">
        <div className="text-red-500 text-lg">{error}</div>
        <button onClick={() => navigate(-1)} className="text-theme-primary underline">返回上一頁</button>
      </div>
    );
  }

  if (!activeContent) {
    return <div className="p-8 text-center text-gray-500">找不到內容</div>;
  }



  return (
    <div className="flex flex-col min-h-screen bg-transparent relative">
      {/* Main Layout Container (Row) - Changed to items-start for sticky functionality */}
      <div id="main-layout-row" className="flex-grow flex flex-row w-full relative items-start">

        {/* 1. Main Content Area (Left, Flexible) */}
        <div className="flex-1 bg-transparent min-w-0">
          <div className={`max-w-[1600px] mx-auto transition-all ${isCitationOpen || isChatOpen ? 'p-6' : 'p-8'} min-h-[calc(100vh-140px)]`}>

            {activeContent && (
              <>
                {/* Title Header Row with Tabs - Sticky */}
                <div className="sticky top-0 z-20 -mx-8 -mt-8 px-8 py-6 mb-8 bg-transparent backdrop-blur-md transition-all">
                  <div className="max-w-[1600px] mx-auto flex flex-col md:flex-row md:items-center justify-between gap-6">
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="text-base px-3 py-1.5 rounded-lg font-bold shadow-sm bg-blue-100 text-blue-700">
                          {itemIndex > 0 && totalItems > 0 ? `第 ${itemIndex} / ${totalItems} 份 ` : ''}
                          {getSubtypeLabel(activeContent.content_type, activeContent.content_subtype)}
                        </span>
                        <h1 className="text-3xl font-bold text-neutral-text-main">
                          <ReactMarkdown components={{ p: ({ children }) => <>{children}</> }}>
                            {activeContent.title}
                          </ReactMarkdown>
                        </h1>
                        {activeContent.is_expired && (
                          <span className="flex items-center gap-1.5 px-2 py-0.5 bg-gray-100 text-gray-500 text-[11px] font-bold rounded-full border border-gray-200 uppercase tracking-wider shadow-sm">
                            期限截止
                          </span>
                        )}
                        {(activeContent.assignment_type === 'file_upload' ? !!fileSubmission : (activeContent.is_submitted || !!quizScore || completedItemIds.includes(activeContent.id))) && (
                          <div className="flex items-center gap-2">
                            <span className="flex items-center gap-1.5 px-2 py-0.5 bg-green-50 text-green-600 text-[11px] font-bold rounded-full border border-green-200 uppercase tracking-wider shadow-sm">
                              <ImCheckmark size={10} />
                              已完成
                            </span>
                            {((activeContent.assignment_type === 'file_upload' && fileSubmission?.is_manual && fileSubmission.score !== null) ||
                              (activeContent.assignment_type !== 'file_upload' && quizScore?.is_manual && quizScore.score !== undefined && quizScore.includeInGrade)) && (
                                <span className={`px-2 py-0.5 text-[11px] font-bold rounded-full border shadow-sm ${(activeContent.assignment_type === 'file_upload' ? fileSubmission!.score! : quizScore!.score!) >= 60
                                  ? 'bg-green-50 text-green-600 border-green-200'
                                  : 'bg-red-50 text-red-600 border-red-200'
                                  }`}>
                                  得分：{activeContent.assignment_type === 'file_upload' ? fileSubmission!.score : quizScore!.score}分
                                </span>
                              )}
                          </div>
                        )}
                      </div>
                      {activeContent.content_type === 'material' && activeContent.duration_minutes && (
                        <div className="flex items-center gap-2 text-sm text-gray-500 mt-2">
                          <span className="bg-gray-100 px-2 py-0.5 rounded text-xs font-medium flex items-center gap-1">
                            ⏱️ {activeContent.duration_minutes} min
                          </span>
                        </div>
                      )}
                    </div>

                    {/* No tab switcher — content and practice render inline */}
                  </div>
                </div>

                {/* Assignment/content description below Title Area - Non-sticky */}
                {activeContent.description && (
                  <div
                    className="mb-8 announcement-content text-neutral-text-main"
                    dangerouslySetInnerHTML={{ __html: activeContent.description }}
                  />
                )}

                {/* Content Rendering Logic */}
                {activeContent.source_type === 'uploaded_content' ? (
                  <div className="bg-gray-50 rounded-xl border-2 border-dashed border-gray-200 p-12 text-center min-h-[500px] flex flex-col items-center justify-center">
                    <div className="inline-flex items-center justify-center w-24 h-24 bg-white rounded-full shadow-sm mb-6">
                      {(() => {
                        const Icon = getFileIcon(activeContent.title);
                        return <Icon size={48} className="text-gray-400" />;
                      })()}
                    </div>
                    <h2 className="text-xl font-bold text-gray-800 mb-2">{activeContent.title}</h2>
                    <p className="text-gray-500 mb-8">此為上傳的完整教材檔案</p>

                    {(() => {
                      const isCompleted = activeContent.is_preview_completed;
                      if (!isCompleted) {
                        return (
                          <div className="flex flex-col items-center justify-center p-8 bg-gray-50 rounded-xl border-2 border-dashed border-gray-200">
                            <div className="bg-gray-200 p-4 rounded-full mb-4">
                              <FaLock className="text-gray-500 text-2xl" />
                            </div>
                            <h3 className="text-lg font-bold text-gray-700 mb-2">教材已鎖定</h3>
                            <p className="text-gray-500 text-center max-w-md">
                              請先完成預習任務（與 AI 互動或通過測驗），<br />獲得足夠的精熟度後即可解鎖下載完整教材。
                            </p>
                          </div>
                        );
                      }
                      const downloadUrl = getMaterialDownloadUrl(activeContent.id);
                      return (
                        <a
                          href={downloadUrl}
                          download
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 px-6 py-3 bg-theme-primary text-white rounded-lg hover:bg-blue-600 transition-colors shadow-lg hover:shadow-xl transform hover:-translate-y-0.5"
                        >
                          <FaDownload />
                          下載完整教材
                        </a>
                      );
                    })()}
                  </div>
                ) : activeContent.content_type === 'material' ? (
                  (() => {
                    try {
                      let innerParsed = parsedContent;
                      // Final unwrap check just in case
                      if (innerParsed && innerParsed.content && !innerParsed.sections) {
                        innerParsed = innerParsed.content;
                      }
                      if (Array.isArray(innerParsed)) {
                        innerParsed = { sections: innerParsed };
                      }

                      return (
                        <div className="space-y-8 animate-in fade-in duration-500">
                          {/* Preview content */}
                          <div className="animate-in fade-in slide-in-from-bottom-2 duration-500">
                            <SummaryContentView
                              summary={innerParsed}
                              materialType={stage as 'preview' | 'review'}
                              editable={false}
                              courseId={courseId || ''}
                              unitId={unitId || ''}
                              contentId={activeContent.id}
                              isTeacher={false}
                              onReferenceClick={handleCitationClick}
                            />
                          </div>

                          {/* Recommended practice questions — rendered inline below content */}
                          {stage !== 'review' && innerParsed?.recommendation_config?.enabled !== false && (
                            <div id="practice-section" className="border-t border-gray-100 pt-6">
                              <RecommendedQuestionsSection
                                key={activeContent?.id}
                                knowledgePointIds={knowledgePointIds}
                                courseId={courseId || ''}
                                stage={stage as 'preview' | 'review'}
                                unitSessionId={unitSessionId}
                                countPerKp={innerParsed?.recommendation_config?.count_per_kp || 3}
                                totalMax={innerParsed?.recommendation_config?.total_max || 10}
                                onComplete={(results) => {
                                  console.log('Results:', results);
                                  if (activeContent) handlePracticeComplete(activeContent.id);
                                }}
                              />
                            </div>
                          )}
                          {stage === 'review' && unitId && (
                            <div className="border-t border-gray-100 pt-6 space-y-8">
                              <ReviewPersonalMaterialsSection
                                unitId={parseInt(unitId)}
                                countPerKp={2}
                                unitSessionId={unitSessionId}
                                onComplete={(results) => console.log('Personal review results:', results)}
                              />
                              <ReviewMasteredQuestionsSection
                                unitId={parseInt(unitId)}
                                unitSessionId={unitSessionId}
                                onComplete={(results) => console.log('Mastered review results:', results)}
                              />
                            </div>
                          )}

                          {/* Navigation Buttons (Bottom) */}
                          <div className="flex flex-col items-center gap-4 pt-4 pb-4 mt-4">
                            <div className="flex flex-wrap justify-center items-center gap-4">
                              {/* Leftmost: Return to list - Gray Style */}
                              <Tooltip content="返回課程清單" position="top">
                                <button
                                  onClick={handleReturnClick}
                                  className="px-8 py-3 bg-white text-gray-700 border border-gray-200 rounded-xl font-bold shadow-sm hover:bg-gray-50 transition-all flex items-center gap-2"
                                >
                                  <span>返回課程列表</span>
                                </button>
                              </Tooltip>

                              {/* Center: Previous item - Secondary Style */}
                              {prevItem && (
                                <Tooltip content={`返回第 ${itemIndex - 1} 份${stage === 'preview' ? '預習' : '複習'}教材：${prevItem.title}`} position="top">
                                  <button
                                    onClick={() => handleNavigateToItem(prevItem)}
                                    className="px-6 py-3 bg-white text-theme-primary border border-theme-primary rounded-xl font-bold shadow-sm hover:bg-blue-50 transition-all flex items-center gap-2"
                                  >
                                    <FaChevronLeft size={14} />
                                    上一份
                                  </button>
                                </Tooltip>
                              )}

                              {/* Right: Next or Finish */}
                              {(() => {
                                if (nextItem) {
                                  return (
                                    <Tooltip content={`前往第 ${itemIndex + 1} 份${stage === 'preview' ? '預習' : '複習'}教材：${nextItem.title}`} position="top">
                                      <button
                                        onClick={() => handleNavigateToItem(nextItem)}
                                        className="px-12 py-3 bg-theme-primary text-white rounded-xl font-bold shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 hover:-translate-y-0.5 transition-all text-lg flex items-center gap-3"
                                      >
                                        <span>下一份：{nextItem.title}</span>
                                        <FaChevronRight size={14} />
                                      </button>
                                    </Tooltip>
                                  );
                                }

                                return (
                                  <Tooltip content="完成閱讀並返回課程大綱" position="top">
                                    <button
                                      onClick={handleCompleteUnitClick}
                                      className="px-12 py-3 bg-theme-primary text-white rounded-xl font-bold shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 hover:-translate-y-0.5 transition-all text-lg flex items-center gap-3"
                                    >
                                      <span>完成閱讀並返回課程</span>
                                      <FaChevronRight size={14} />
                                    </button>
                                  </Tooltip>
                                );
                              })()}
                            </div>
                          </div>
                        </div>
                      );
                    } catch (error) {
                      return (
                        <div className="bg-red-50 border-2 border-red-200 rounded-xl p-8 text-center">
                          <h3 className="text-lg font-bold text-red-700 mb-2">無法顯示摘要內容</h3>
                          <p className="text-red-600 text-sm">生成的內容結構不完整或有誤。</p>
                        </div>
                      );
                    }
                  })()
                ) : (activeContent.content_type === 'assignment' || activeContent.content_type === 'exam') && activeContent.assignment_type === 'file_upload' ? (
                  <div className="space-y-6">
                    {/* 截止時間提示 */}
                    {activeContent.end_time && (
                      <div className={`flex items-center gap-3 text-sm px-5 py-3 rounded-xl border border-gray-100 bg-white shadow-sm border-l-4 ${isPastDeadline
                        ? 'border-l-red-500 text-red-700'
                        : 'border-l-blue-500 text-blue-700'
                        }`}>
                        <span className="font-bold flex items-center gap-2">
                          {isPastDeadline ? '⛔ 繳交截止：' : '⏰ 截止時間：'}
                        </span>
                        <span className="opacity-80">
                          {formatDateTime(activeContent.end_time)}
                        </span>
                      </div>
                    )}

                    {/* 已繳交記錄 */}
                    {fileSubmission && (
                      <div className="bg-white border border-gray-100 border-l-4 border-l-green-500 rounded-xl shadow-sm overflow-hidden">
                        <div className="p-5">
                          <div className="flex items-start gap-4">
                            <div className="p-2 bg-green-50 rounded-lg">
                              <FaCheckCircle className="text-green-500" size={20} />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between">
                                <h4 className="font-bold text-gray-800 flex items-center gap-2">
                                  已繳交紀錄
                                  <span className="px-2 py-0.5 bg-green-50 text-green-600 text-[10px] rounded-full font-medium">
                                    {fileSubmission.files?.length || 0} 個檔案
                                  </span>
                                </h4>
                              </div>

                              {fileSubmission.feedback && (
                                <div className="mt-4 space-y-3 animate-in fade-in slide-in-from-top-2 duration-500">
                                  <div className="pl-3.5 py-1 border-l-2 border-green-100">
                                    <p className="text-xs text-gray-500 leading-relaxed italic">
                                      <span className="text-green-600 font-bold not-italic mr-1.5">評語：</span>
                                      {fileSubmission.feedback}
                                    </p>
                                  </div>
                                </div>
                              )}

                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
                                {fileSubmission.files && fileSubmission.files.map((file) => (
                                  <div key={file.name} className="flex items-center justify-between p-3 bg-gray-50/50 rounded-xl border border-gray-100 group hover:bg-white hover:shadow-md transition-all duration-300">
                                    <div className="flex items-center gap-3 overflow-hidden">
                                      <div className="p-2 bg-white rounded-lg shadow-sm">
                                        <FaFileAlt className="text-blue-500" size={16} />
                                      </div>
                                      <div className="min-w-0">
                                        <p className="text-xs font-bold text-gray-700 truncate">{file.original_name}</p>
                                        <p className="text-[10px] text-gray-400">
                                          {(file.size / 1024).toFixed(1)} KB • {formatDateOnly(file.uploaded_at)}
                                        </p>
                                      </div>
                                    </div>
                                    <div className="flex items-center gap-1 opacity-100 sm:opacity-0 group-hover:opacity-100 transition-opacity">
                                      <a
                                        href={`${import.meta.env.VITE_API_URL || '/api/v1'}/api/student/file-submissions/${activeContent.id}/download/${file.name}`}
                                        className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
                                        title="下載檔案"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        onClick={(e) => {
                                          const token = sessionStorage.getItem('access_token');
                                          if (token) {
                                            e.preventDefault();
                                            fetch(e.currentTarget.href, {
                                              headers: { 'Authorization': `Bearer ${token}` }
                                            }).then(res => res.blob()).then(blob => {
                                              const url = window.URL.createObjectURL(blob);
                                              const a = document.createElement('a');
                                              a.href = url;
                                              a.download = file.original_name;
                                              a.click();
                                            });
                                          }
                                        }}
                                      >
                                        <FaDownload size={14} />
                                      </a>
                                      {!isPastDeadline && fileSubmission.score === null && (
                                        <button
                                          onClick={async (e) => {
                                            e.preventDefault();
                                            e.stopPropagation();
                                            setConfirmConfig({
                                              title: '確認刪除',
                                              message: `確定要刪除 ${file.original_name} 嗎？`,
                                              type: 'danger',
                                              onConfirm: async () => {
                                                try {
                                                  const updated = await deleteFileSubmissionFile(activeContent.id, file.name);
                                                  setFileSubmission(updated);
                                                  setShowConfirmDialog(false);
                                                  setToast({ show: true, message: '檔案已刪除', type: 'success' });
                                                } catch (err: any) {
                                                  alert(err.message || '刪除失敗');
                                                }
                                              }
                                            });
                                            setShowConfirmDialog(true);
                                          }}
                                          className="p-2 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                                          title="刪除檔案"
                                        >
                                          <FaTrash size={14} />
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {isPastDeadline ? (
                      !fileSubmission && (
                        <div className="bg-white border border-gray-100 border-l-4 border-l-gray-400 rounded-xl p-8 text-center shadow-sm">
                          <FaTimesCircle className="mx-auto text-gray-300 mb-3" size={40} />
                          <p className="font-bold text-gray-600">繳交逾期，且無繳交記錄</p>
                          <p className="text-sm text-gray-400 mt-1">作業截止前未收到您的任何檔案。</p>
                        </div>
                      )
                    ) : (!fileSubmission || fileSubmission.score === null) && (
                      <>
                        <div
                          className={`bg-white rounded-2xl border-2 border-dashed p-10 text-center transition-all cursor-pointer shadow-sm ${isDragOver
                            ? 'border-blue-500 bg-blue-50/30'
                            : selectedFile
                              ? 'border-green-400 bg-green-50/30'
                              : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50/50'
                            }`}
                          onClick={() => fileInputRef.current?.click()}
                          onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                          onDragLeave={() => setIsDragOver(false)}
                          onDrop={(e) => {
                            e.preventDefault();
                            setIsDragOver(false);
                            const file = e.dataTransfer.files[0];
                            if (file) {
                              setSelectedFile(file);
                              setUploadError(null);
                            }
                          }}
                        >
                          <input
                            ref={fileInputRef}
                            type="file"
                            className="hidden"
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              if (file) {
                                setSelectedFile(file);
                                setUploadError(null);
                              }
                            }}
                          />
                          {selectedFile ? (
                            <div className="space-y-2">
                              <FaFileAlt className="mx-auto text-green-500" size={40} />
                              <p className="font-bold text-gray-800">{selectedFile.name}</p>
                              <p className="text-sm text-gray-500">{(selectedFile.size / 1024).toFixed(1)} KB</p>
                              <p className="text-xs text-gray-400">點擊更換檔案</p>
                            </div>
                          ) : (
                            <div className="space-y-3">
                              <FaCloudUploadAlt className="mx-auto text-gray-400" size={48} />
                              <p className="font-semibold text-gray-700">點擊或拖放檔案至此處</p>
                              <p className="text-sm text-gray-400">支援 PDF, Word, PowerPoint, 圖片等格式 (最大 50MB)</p>
                            </div>
                          )}
                        </div>
                        {uploadError && (
                          <div className="flex items-center gap-2 text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg p-3">
                            <FaTimesCircle />
                            <span>{uploadError}</span>
                          </div>
                        )}
                        {selectedFile && (
                          <div className="flex justify-center">
                            <button
                              onClick={async (e) => {
                                e.stopPropagation();
                                if (!selectedFile || !activeContent) return;
                                setIsUploading(true);
                                setUploadError(null);
                                try {
                                  const result = await uploadFileSubmission(activeContent.id, selectedFile);
                                  setFileSubmission(result);
                                  setSelectedFile(null);
                                  setToast({ show: true, message: '檔案上傳成功！', type: 'success' });
                                } catch (err: any) {
                                  setUploadError(err.message || '上傳失敗，請稍後再試');
                                } finally {
                                  setIsUploading(false);
                                }
                              }}
                              disabled={isUploading}
                              className="px-8 py-3 bg-blue-600 text-white rounded-xl font-bold shadow-lg hover:bg-blue-700 disabled:opacity-50 transition-all flex items-center gap-2"
                            >
                              {isUploading ? (
                                <><FaSpinner className="animate-spin" /> 上傳中...</>
                              ) : (
                                <><FaCloudUploadAlt /> 繳交新檔案</>
                              )}
                            </button>
                          </div>
                        )}

                      </>
                    )}

                    {/* Navigation Button (Bottom) - Always visible */}
                    <div className="flex justify-center pt-8 border-t border-gray-100 mt-8">
                      <button
                        onClick={handleReturnClick}
                        className="px-8 py-3 bg-white text-gray-700 border border-gray-200 rounded-xl font-bold shadow-sm hover:bg-gray-50 transition-all flex items-center gap-2"
                      >
                        <FaChevronLeft size={14} className="text-gray-400" />
                        <span>返回課程列表</span>
                      </button>
                    </div>
                  </div>
                ) : (activeContent.content_type === 'assignment' || activeContent.content_type === 'exam') ? (
                  <ShortAnswerQuizSection
                    knowledgePointId={activeContent.knowledge_points?.[0]?.id || 0}
                    knowledgePointName={activeContent.knowledge_points?.[0]?.name}
                    questions={extractedQuestions}
                    unitSessionId={unitSessionId}
                    onEvaluationComplete={(results: EvaluationResult[]) => {
                      console.log('Quiz evaluation complete:', results);
                    }}
                    onCitationClick={handleCitationClick}
                    onReturnToCourse={handleReturnClick}
                    contentType={activeContent.content_type as any}
                    contentId={activeContent.id}
                    showAnswersAfter={activeContent.show_answers_after}
                    durationMinutes={activeContent.duration_minutes}

                    isExpired={activeContent.is_expired}
                    nextItem={nextItem}
                    prevItem={prevItem}
                    onNavigateToItem={handleNavigateToItem}
                    onScoreLoaded={setQuizScore}
                  />
                ) : (
                  <div className="text-center p-12 text-gray-500 bg-gray-50/50 rounded-2xl border border-dashed border-gray-200">
                    <p className="mb-6">不支援的內容類型: {activeContent.content_type}</p>
                    <button
                      onClick={handleReturnClick}
                      className="px-8 py-3 bg-white text-gray-700 border border-gray-200 rounded-xl font-bold shadow-sm hover:bg-gray-50 transition-all inline-flex items-center gap-2"
                    >
                      <span>返回課程列表</span>
                    </button>
                  </div>
                )}

                {/* Knowledge Points Footer */}
                {activeContent.knowledge_points && activeContent.knowledge_points.length > 0 && (
                  <div className="mt-12 pt-8 border-t border-gray-100">
                    <h3 className="text-sm font-bold text-gray-500 mb-3">關聯知識點</h3>
                    <div className="flex flex-wrap gap-2">
                      {activeContent.knowledge_points.map(kp => (
                        <span key={kp.id} className="px-3 py-1 bg-gray-100 text-gray-600 rounded-full text-xs font-medium">
                          {kp.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* 2. Citation Sidebar (Middle, Resizable) - Added sticky */}
        {
          isCitationOpen && selectedCitation && (
            <div
              className="bg-white flex flex-col shadow-2xl z-20 shrink-0 relative transition-none sticky top-6 rounded-2xl border border-gray-100 m-2 ml-0 overflow-hidden"
              style={{ width: `${citationWidth}px`, height: typeof sidebarHeight === 'number' ? `${sidebarHeight}px` : sidebarHeight }}
            >
              {/* Citation Resize Handle (Left) */}
              <div
                className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-theme-primary/50 group z-50 transition-colors flex items-center justify-center -ml-0.5"
                onMouseDown={() => setActiveResizer('citation')}
              >
                <div className="w-0.5 h-8 bg-gray-300 rounded-full group-hover:bg-theme-primary"></div>
              </div>

              {/* Header */}
              <div className="flex-none flex items-center justify-between px-4 py-3 border-b border-blue-100 bg-gradient-to-r from-blue-50 via-cyan-50 to-blue-50 h-[52px]">
                <h3 className="text-base font-bold bg-gradient-to-r from-blue-700 to-cyan-600 bg-clip-text text-transparent flex items-center gap-2">
                  <FaLink size={14} className="text-blue-600" /> 引用來源詳情
                </h3>
                <button
                  onClick={closeCitationSidebar}
                  className="p-1 rounded-full text-gray-500 hover:bg-white/80 hover:text-blue-600 transition-colors"
                  title="關閉"
                >
                  <FaChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-y-auto p-4 bg-gray-50/30 min-h-0">
                <div className="flex flex-col gap-3 mb-4">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-base text-gray-800 break-all leading-snug">
                      {selectedCitation.fullChunk?.source || '未知來源'}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2 text-xs">
                    {/* Page Display */}
                    {selectedCitation.fullChunk?.page_number && (
                      <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded-md font-medium whitespace-nowrap border border-gray-200">
                        Page {selectedCitation.fullChunk.page_number}
                      </span>
                    )}

                    {/* Match Score Badge */}
                    {selectedCitation.matchScore !== undefined && (
                      <div className={`flex flex-shrink-0 items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border ${selectedCitation.matchScore >= 80
                        ? 'bg-green-50 text-green-700 border-green-200'
                        : selectedCitation.matchScore >= 60
                          ? 'bg-yellow-50 text-yellow-700 border-yellow-200'
                          : 'bg-red-50 text-red-700 border-red-200'
                        }`}>
                        <span>{Math.round(selectedCitation.matchScore)}% Match</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* PDF Viewer - Show original document page */}
                {selectedCitation.fullChunk?.source && (
                  <div className="flex-1 min-h-0 bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden relative">
                    {(() => {
                      const sourceName = selectedCitation.fullChunk.source;
                      const safeName = sourceName?.trim() || '';
                      const lowerName = safeName.toLowerCase();

                      let targetPdfName = safeName;
                      let isPdfOrOffice = false;

                      // Support PDF natively
                      if (lowerName.endsWith('.pdf')) {
                        isPdfOrOffice = true;
                      }
                      // For Office files (pptx, docx), try to load the corresponding PDF
                      // The RAG process often generates a PDF version for indexing
                      else if (lowerName.endsWith('.pptx') || lowerName.endsWith('.ppt') ||
                        lowerName.endsWith('.docx') || lowerName.endsWith('.doc')) {
                        isPdfOrOffice = true;
                        // Replace extension with .pdf
                        targetPdfName = safeName.substring(0, safeName.lastIndexOf('.')) + '.pdf';
                        console.log(`[TopicPreview] Attempting to view Office file as PDF: ${safeName} -> ${targetPdfName}`);
                      }

                      if (isPdfOrOffice) {
                        console.log('[TopicPreview] Rendering PDFViewer for:', targetPdfName);
                        return (
                          <PDFViewer
                            documentId={selectedCitation.fullChunk.source_metadata?.document_id}
                            documentName={targetPdfName}
                            pageNumber={selectedCitation.fullChunk.page_number}
                            fallbackContent={selectedCitation.evidence}
                            className="h-full"
                          />
                        );
                      }

                      console.log('[TopicPreview] Rendering Fallback (Evidence Only) for:', safeName);
                      // Use PDFViewer's fallback logic even for non-PDF types to show elegant evidence view
                      // This effectively removes the download button as requested.
                      return (
                        <PDFViewer
                          fallbackContent={selectedCitation.evidence}
                          className="h-full"
                        />
                      );
                    })()}
                  </div>
                )}
              </div>
            </div>
          )
        }

        {/* 3. AI Chatbot (Right, Collapsible & Resizable) - Added sticky */}
        {
          (activeContent.content_subtype !== 'quiz' &&
            activeContent.content_subtype !== 'midterm' &&
            activeContent.content_subtype !== 'final') && (
            isChatOpen ? (
              <div
                className="bg-white flex flex-col shadow-2xl z-30 shrink-0 relative transition-none sticky top-6 rounded-2xl border border-gray-100 m-2 ml-0 overflow-hidden"
                style={{ width: `${chatWidth}px`, height: 'calc(100vh - 120px)' }}
              >
                {/* Chat Resize Handle (Left) */}
                <div
                  className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-theme-primary/50 group z-50 transition-colors flex items-center justify-center -ml-0.5"
                  onMouseDown={() => setActiveResizer('chat')}
                >
                  <div className="w-0.5 h-8 bg-gray-300 rounded-full group-hover:bg-theme-primary"></div>
                </div>

                {/* Header */}
                <div className="flex-none flex items-center justify-between px-4 py-3 border-b border-blue-100 bg-gradient-to-r from-blue-50 via-cyan-50 to-blue-50 h-[52px]">
                  <div className="flex items-center gap-2">
                    <div className="p-1 bg-white rounded-lg shadow-sm text-blue-600">
                      <FaRobot size={14} />
                    </div>
                    <h3 className="text-base font-bold bg-gradient-to-r from-blue-700 to-cyan-600 bg-clip-text text-transparent">
                      AI 學習助手
                    </h3>
                  </div>

                  <button
                    onClick={() => setIsChatOpen(false)}
                    className="text-gray-400 hover:text-gray-600 p-1 rounded-md hover:bg-white/50 transition-colors"
                    title="收起"
                  >
                    <FaChevronRight size={12} />
                  </button>
                </div>

                {/* Chat History */}
                <div ref={chatHistoryRef} className="flex-grow overflow-y-auto p-3 space-y-3 bg-gray-50/50 min-h-0">
                  {isLoadingChatHistory && (
                    <div className="text-center text-gray-400 text-sm py-2">載入對話紀錄中...</div>
                  )}
                  {chatHistory.map((msg, index) => (
                    <div key={index} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[90%] rounded-2xl p-3 shadow-md ${msg.role === 'user'
                        ? 'bg-blue-600 text-white rounded-tr-none'
                        : 'bg-white border border-gray-100 text-neutral-text-main rounded-tl-none'
                        }`}>
                        <div className="text-sm leading-relaxed">
                          {msg.role === 'ai' ? (() => {
                            // Build citation map: [doc:X] → [N] in order of first appearance
                            const docIdToNum = new Map<string, number>();
                            let counter = 1;
                            const processedText = msg.text.replace(/\[doc:(\d+)\]/g, (_: string, id: string) => {
                              if (!docIdToNum.has(id)) docIdToNum.set(id, counter++);
                              return `[${docIdToNum.get(id)}]`;
                            });
                            // Assign numbers to sources; if LLM cited none (fallback), number sequentially
                            const hasCitations = docIdToNum.size > 0;
                            const numberedSources = (msg.sources ?? []).map((s: SourceItem, i: number) => ({
                              ...s,
                              num: hasCitations ? docIdToNum.get(String(s.chunk_id)) ?? null : i + 1,
                            })).filter(s => s.num !== null).sort((a, b) => (a.num as number) - (b.num as number));
                            return (
                              <>
                                <ReactMarkdown
                                  remarkPlugins={[remarkGfm]}
                                  components={{
                                    code: ({ node, className, children, ...props }) => {
                                      const match = /language-(\w+)/.exec(className || '')
                                      const isInline = !match && !String(children).includes('\n');
                                      return isInline ? (
                                        <code className="bg-black/10 rounded px-1.5 py-0.5 text-[0.9em] font-mono break-all" {...props}>
                                          {children}
                                        </code>
                                      ) : (
                                        <code className="block bg-black/10 rounded p-2 text-xs font-mono overflow-x-auto my-2 whitespace-pre-wrap" {...props}>
                                          {children}
                                        </code>
                                      )
                                    },
                                    table: ({ node, ...props }) => (
                                      <table style={{ borderCollapse: 'collapse', width: '100%', margin: '8px 0', fontSize: '12px' }} {...props} />
                                    ),
                                    th: ({ node, ...props }) => (
                                      <th style={{ border: '1px solid #d1d5db', padding: '4px 8px', background: '#f3f4f6', textAlign: 'left', fontWeight: 600 }} {...props} />
                                    ),
                                    td: ({ node, ...props }) => (
                                      <td style={{ border: '1px solid #d1d5db', padding: '4px 8px' }} {...props} />
                                    ),
                                  }}
                                >
                                  {processedText}
                                </ReactMarkdown>
                                {numberedSources.length > 0 && (
                                  <div className="mt-2 pt-2 border-t border-gray-100/50 text-[10px]">
                                    <div className="font-semibold opacity-70 mb-1">參考來源:</div>
                                    <ol className="space-y-0.5 list-none pl-0">
                                      {numberedSources.map((source, idx) => (
                                        <li key={idx} className="flex items-start gap-1 opacity-80">
                                          <span className="shrink-0 font-medium">{source.num}.</span>
                                          <span>{source.source_filename || source.title || '未知來源'}{source.page_numbers ? ` (p.${source.page_numbers})` : ''}</span>
                                        </li>
                                      ))}
                                    </ol>
                                  </div>
                                )}
                              </>
                            );
                          })() : msg.text}
                        </div>
                      </div>
                    </div>
                  ))}
                  {isLoadingChat && (
                    <div className="flex justify-start">
                      <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-none p-3 shadow-sm flex items-center gap-2 text-gray-500">
                        <FaSpinner className="animate-spin text-theme-primary" size={12} />
                        <span className="text-xs">思考中...</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Input Area */}
                <div className="p-3 bg-white border-t border-neutral-border shrink-0">
                  <form onSubmit={handleSendMessage} className="relative">
                    <input
                      type="text"
                      value={chatMessage}
                      onChange={(e) => setChatMessage(e.target.value)}
                      placeholder="有問題隨時問我..."
                      className="w-full pl-3 pr-10 py-2.5 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:border-theme-primary focus:ring-2 focus:ring-theme-primary/20 transition-all text-sm"
                      disabled={isLoadingChat}
                    />
                    <button
                      type="submit"
                      disabled={!chatMessage.trim() || isLoadingChat}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1.5 bg-theme-primary text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:hover:bg-theme-primary transition-colors shadow-sm"
                    >
                      <FaPaperPlane size={12} />
                    </button>
                  </form>
                </div>
              </div>
            ) : (
              <div className="sticky top-6 z-50 shrink-0 self-start mr-6 mt-6">
                <Tooltip content="展開 AI 助手" position="left">
                  <button
                    onClick={() => setIsChatOpen(true)}
                    className="w-12 h-12 bg-white text-theme-primary border border-gray-200 rounded-full shadow-lg flex items-center justify-center hover:bg-gray-50 hover:scale-105 transition-all duration-300"
                  >
                    <FaRobot size={20} />
                  </button>
                </Tooltip>
              </div>
            ))
        }
      </div>

      {/* Material Rating Modal */}
      <MaterialRatingModal
        isOpen={isRatingModalOpen}
        onClose={handleRatingCancel}
        onSubmitSuccess={handleRatingSubmitSuccess}
        onReturn={handleRatingSubmitSuccess}
        contentIds={sessionCompletedIds}
      />

      {/* Completion Confirmation Dialog */}
      {confirmConfig && (
        <ConfirmDialog
          isOpen={showConfirmDialog}
          onClose={() => setShowConfirmDialog(false)}
          onCancel={() => setShowConfirmDialog(false)}
          onConfirm={confirmConfig.onConfirm}
          title={confirmConfig.title}
          message={confirmConfig.message}
          confirmText={confirmConfig.confirmLabel || '確定'}
          cancelText={confirmConfig.cancelLabel || '取消'}
          variant={confirmConfig.type === 'info' ? 'warning' : (confirmConfig.type as any) || 'warning'}
        />
      )}

      {toast.show && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast({ ...toast, show: false })}
        />
      )}
    </div>
  );
};

export default TopicPreview;
