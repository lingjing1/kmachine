
import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import {
    FaChevronLeft,
    FaChevronRight,
    FaFileAlt,
    FaFileImage,
    FaDownload
} from 'react-icons/fa';
import {
    getAttachmentView,
    getAttachmentBlob,
    logAttachmentReadingTime,
    sendMessage,
    getConversations,
    getConversationMessages,
    AttachmentViewResponse,
    PPTXSlide,
} from '../../services/studentApi';
import { Document, Page, pdfjs } from 'react-pdf';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FaRobot, FaPaperPlane, FaSpinner } from 'react-icons/fa';
import 'react-pdf/dist/Page/TextLayer.css';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import API_BASE_URL from '../../config/api';

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

const AttachmentViewer: React.FC = () => {
    const { courseId, unitId, attachmentId } = useParams<{ courseId: string; unitId: string; attachmentId: string }>();
    const navigate = useNavigate();
    const location = useLocation();
    const [loading, setLoading] = useState(true);
    const [viewData, setViewData] = useState<AttachmentViewResponse | null>(null);
    const [currentSlide, setCurrentSlide] = useState(0);
    const [pdfNumPages, setPdfNumPages] = useState<number | null>(null);
    const [error, setError] = useState<string | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const innerPdfRef = useRef<HTMLDivElement>(null);
    const [containerWidth, setContainerWidth] = useState(0);

    // State for idle detection and cumulative time
    const [activeSeconds, setActiveSeconds] = useState(0);
    const lastActivityRef = useRef<number>(Date.now());
    const isIdleRef = useRef<boolean>(false);
    const IDLE_THRESHOLD = 30000; // 30 seconds
    const intervalRef = useRef<any>(null);

    // Chatbot States
    // Chatbot States
    const WELCOME_MESSAGE = { role: 'ai', text: '你好！我是你的 AI 學習助手。關於這個附件內容有任何問題都可以問我喔！' };
    const [isChatOpen, setIsChatOpen] = useState(true);
    const [chatMessage, setChatMessage] = useState('');
    const [chatHistory, setChatHistory] = useState<any[]>([WELCOME_MESSAGE]);
    const [conversationId, setConversationId] = useState<string | null>(null);
    const [isLoadingChat, setIsLoadingChat] = useState(false);
    const [isLoadingChatHistory, setIsLoadingChatHistory] = useState(true);
    const chatHistoryRef = useRef<HTMLDivElement>(null);
    const [chatWidth, setChatWidth] = useState(400);
    const [activeResizer, setActiveResizer] = useState<'chat' | null>(null);

    // 進入頁面時，還原這個附件既有的對話紀錄（如果有的話）
    useEffect(() => {
        let cancelled = false;

        const loadChatHistory = async () => {
            if (!courseId || !unitId) return;
            setIsLoadingChatHistory(true);
            try {
                const result = await getConversations({
                    courseId: parseInt(courseId),
                    unitId: parseInt(unitId),
                    attachmentId: attachmentId ? parseInt(attachmentId) : undefined,
                });

                if (cancelled) return;

                const latest = result.conversations?.[0];
                if (!latest) {
                    setConversationId(null);
                    setChatHistory([WELCOME_MESSAGE]);
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
                    setChatHistory([WELCOME_MESSAGE]);
                }
            } finally {
                if (!cancelled) setIsLoadingChatHistory(false);
            }
        };

        loadChatHistory();

        return () => {
            cancelled = true;
        };
    }, [courseId, unitId, attachmentId]);

    // Dynamic Sidebar Height (same logic as TopicPreview)
    const [sidebarHeight, setSidebarHeight] = useState<number | string>('calc(100vh - 120px)');
    const lastHeightRef = useRef<number>(0);

    // Get attachment title from navigation state if available
    const { title: attachmentTitle = '附件內容', fileType } = (location.state as any) || {};

    // Dynamic Sidebar Height Effect
    useEffect(() => {
        const calculateHeight = () => {
            const footer = document.getElementById('app-footer');
            const row = document.getElementById('attachment-layout-row');
            if (!row) return;
            const viewportHeight = window.innerHeight;
            const footerRect = footer?.getBoundingClientRect();
            const rowRect = row.getBoundingClientRect();
            const topGap = Math.max(24, rowRect.top + 24);
            let bottomGap = 24;
            if (footerRect && footerRect.top < viewportHeight) {
                bottomGap = Math.max(24, (viewportHeight - footerRect.top) + 24);
            }
            const newHeight = Math.max(300, viewportHeight - topGap - bottomGap);
            if (Math.abs(newHeight - lastHeightRef.current) > 2) {
                lastHeightRef.current = newHeight;
                setSidebarHeight(newHeight);
            }
        };
        const row = document.getElementById('attachment-layout-row');
        const scrollContainer = row?.closest('.overflow-y-auto') || window;
        scrollContainer.addEventListener('scroll', calculateHeight, { passive: true });
        window.addEventListener('resize', calculateHeight);
        calculateHeight();
        return () => {
            scrollContainer.removeEventListener('scroll', calculateHeight);
            window.removeEventListener('resize', calculateHeight);
        };
    }, []);


    useEffect(() => {
        const fetchContent = async () => {
            if (!attachmentId) return;
            setLoading(true);
            try {
                // Check if PDF based on passed fileType or fallback to filename extension
                const isPdf = (fileType === 'pdf' || fileType === 'application/pdf') ||
                    attachmentTitle.toLowerCase().endsWith('.pdf');

                if (isPdf) {
                    const blob = await getAttachmentBlob(Number(attachmentId));
                    const url = URL.createObjectURL(blob);
                    setViewData({ type: 'pdf', content: url });
                } else {
                    const data = await getAttachmentView(Number(attachmentId));
                    setViewData(data);
                }
            } catch (err: any) {
                console.error('Failed to fetch attachment content:', err);
                setError(err.message || '無法載入附件內容');
            } finally {
                setLoading(false);
            }
        };

        fetchContent();

        // 1. Activity listeners
        const handleActivity = () => {
            lastActivityRef.current = Date.now();
            isIdleRef.current = false;
        };

        window.addEventListener('mousemove', handleActivity);
        window.addEventListener('keydown', handleActivity);
        window.addEventListener('click', handleActivity);
        window.addEventListener('scroll', handleActivity, true);

        // 2. Timer interval (every 1 second)
        intervalRef.current = setInterval(() => {
            const now = Date.now();
            if (now - lastActivityRef.current < IDLE_THRESHOLD) {
                setActiveSeconds(prev => prev + 1);
            } else {
                isIdleRef.current = true;
            }
        }, 1000);

        // 3. Periodic logging (every 30 seconds)
        const loggingInterval = setInterval(() => {
            setActiveSeconds(prev => {
                if (prev >= 5 && attachmentId) {
                    logAttachmentReadingTime(Number(attachmentId), prev)
                        .catch(err => console.error('Heartbeat log failed:', err));
                    return 0; // Reset after successful log
                }
                return prev;
            });
        }, 30000);

        return () => {
            window.removeEventListener('mousemove', handleActivity);
            window.removeEventListener('keydown', handleActivity);
            window.removeEventListener('click', handleActivity);
            window.removeEventListener('scroll', handleActivity, true);
            if (intervalRef.current) clearInterval(intervalRef.current);
            clearInterval(loggingInterval);

            // Final log — use sendBeacon for reliability on page unload
            setActiveSeconds(finalSeconds => {
                if (finalSeconds > 2 && attachmentId) {
                    const url = `/api/attachments/${attachmentId}/reading-time`;
                    const payload = JSON.stringify({ reading_time_seconds: finalSeconds });
                    const blob = new Blob([payload], { type: 'application/json' });
                    // sendBeacon doesn't support auth headers, so also fire async as backup
                    navigator.sendBeacon(url, blob);
                    logAttachmentReadingTime(Number(attachmentId), finalSeconds)
                        .catch(() => { });
                }
                return 0;
            });

            // Cleanup blob URL if it was created
            if (viewData && viewData.type === 'pdf' && viewData.content) {
                URL.revokeObjectURL(viewData.content as string);
            }
        };
    }, [attachmentId, attachmentTitle]);

    // 量測 PDF 內層可用寬度
    useEffect(() => {
        const el = innerPdfRef.current;
        if (!el) return;
        const ro = new ResizeObserver(() => {
            setContainerWidth(el.clientWidth);
        });
        ro.observe(el);
        return () => ro.disconnect();
    }, [viewData?.type]); // PDF mount 後才有 innerPdfRef

    // Chat Scroll Effect
    useEffect(() => {
        if (chatHistoryRef.current) {
            chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
        }
    }, [chatHistory, isChatOpen]);

    // Resizer Logic
    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!activeResizer) return;
            e.preventDefault();
            const newWidth = window.innerWidth - e.clientX;
            if (newWidth >= 300 && newWidth <= 800) {
                setChatWidth(newWidth);
            }
        };
        const handleMouseUp = () => {
            setActiveResizer(null);
        };
        if (activeResizer) {
            window.addEventListener('mousemove', handleMouseMove);
            window.addEventListener('mouseup', handleMouseUp);
        }
        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, [activeResizer]);


    const handleSendMessage = async (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!chatMessage.trim() || isLoadingChat) return;

        const userMsg = chatMessage;
        setChatMessage('');
        setChatHistory(prev => [...prev, { role: 'user', text: userMsg }]);
        setIsLoadingChat(true);

        try {
            const response = await sendMessage({
                message: userMsg,
                conversation_id: conversationId || undefined,
                course_id: parseInt(courseId!),
                unit_id: unitId ? parseInt(unitId) : undefined as any,
                attachment_id: attachmentId ? parseInt(attachmentId) : undefined,
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

    const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
        setPdfNumPages(numPages);
    };

    const handleBack = () => {
        navigate(`/student/course/${courseId}`);
    };

    const handleFinish = async () => {
        // Log remaining time before navigating back
        if (activeSeconds > 0 && attachmentId) {
            try {
                await logAttachmentReadingTime(Number(attachmentId), activeSeconds);
            } catch (err) {
                console.error('Failed to log final time on finish:', err);
            }
        }
        handleBack();
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-neutral-bg flex flex-col items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-theme-primary mb-4"></div>
                <p className="text-neutral-text-secondary">內容載入中...</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="min-h-screen bg-neutral-bg flex flex-col items-center justify-center p-6 text-center">
                <div className="bg-white p-8 rounded-2xl shadow-sm border border-neutral-border max-w-md">
                    <div className="text-red-500 text-4xl mb-4 flex justify-center">⚠️</div>
                    <h3 className="text-xl font-bold text-neutral-text-main mb-2">出錯了</h3>
                    <p className="text-neutral-text-secondary mb-6">{error}</p>
                    <button
                        onClick={handleBack}
                        className="px-6 py-2 bg-theme-primary text-white rounded-xl font-medium"
                    >
                        返回課程
                    </button>
                </div>
            </div>
        );
    }

    const renderContent = () => {
        if (!viewData) return null;

        switch (viewData.type) {
            case 'pdf':
                return (
                    <div ref={containerRef} className="w-full flex flex-col bg-white rounded-2xl shadow-xl overflow-hidden border border-neutral-100">
                        {/* PDF Content Area - 連續捲動模式 */}
                        <div ref={innerPdfRef} className="flex flex-col items-center py-6 gap-4 bg-neutral-50/30">
                            {viewData.content && (
                                <Document
                                    file={viewData.content as string}
                                    onLoadSuccess={onDocumentLoadSuccess}
                                    loading={
                                        <div className="flex flex-col items-center gap-4 py-20">
                                            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-theme-primary"></div>
                                            <p className="text-neutral-text-tertiary">PDF 解析中...</p>
                                        </div>
                                    }
                                    error={
                                        <div className="text-neutral-text-main bg-red-50 p-6 rounded-xl border border-red-100 text-center">
                                            無法渲染 PDF 文件
                                        </div>
                                    }
                                >
                                    {Array.from(new Array(pdfNumPages || 0), (_, index) => (
                                        <Page
                                            key={`page_${index + 1}`}
                                            pageNumber={index + 1}
                                            width={containerWidth > 0 ? Math.floor(containerWidth * 0.8) : undefined}
                                            renderTextLayer={true}
                                            renderAnnotationLayer={true}
                                            className="shadow-md border border-neutral-200"
                                        />
                                    ))}
                                </Document>
                            )}
                        </div>

                        {/* Page Count */}
                        {pdfNumPages && (
                            <div className="bg-white border-t border-neutral-100 p-2 flex items-center justify-center">
                                <span className="text-xs font-bold text-neutral-text-tertiary">
                                    共 {pdfNumPages} 頁
                                </span>
                            </div>
                        )}
                    </div>
                );

            case 'html':
                return (
                    <div className="w-full flex justify-center py-4 md:py-8 bg-neutral-100/30 min-h-[70vh]">
                        {/* Word Paper Simulation */}
                        <div className="w-full max-w-[850px] bg-white shadow-2xl rounded-sm p-12 md:p-20 border border-neutral-200 relative overflow-hidden">
                            {/* Decorative Page Line */}
                            <div className="absolute top-0 left-0 w-full h-1 bg-blue-500/10"></div>

                            <div
                                className="prose prose-slate prose-lg md:prose-xl max-w-none prose-headings:text-neutral-text-main prose-headings:font-black prose-p:text-neutral-text-main prose-p:leading-relaxed prose-img:rounded-xl prose-img:shadow-lg"
                                dangerouslySetInnerHTML={{ __html: viewData.content as string }}
                            />

                            {/* Decorative Footer info */}
                            <div className="mt-20 pt-8 border-t border-neutral-100 flex justify-between items-center text-xs text-neutral-text-tertiary italic">
                                <span>End of Document</span>
                                <span>{attachmentTitle}</span>
                            </div>
                        </div>
                    </div>
                );

            case 'pptx':
                const slides = viewData.content as PPTXSlide[];
                if (!slides || slides.length === 0) return <div>簡報無內容</div>;

                const slide = slides[currentSlide];

                return (
                    <div className="w-full max-w-5xl mx-auto flex flex-col bg-white rounded-xl shadow-2xl overflow-hidden" style={{ height: '75vh' }}>
                        <div className="flex-grow relative group overflow-hidden">
                            {/* Slide Content */}
                            <div className="h-full flex flex-col p-4 md:p-6 bg-neutral-50/30 overflow-auto">
                                <div className="max-w-4xl mx-auto w-full space-y-4">
                                    {/* Images */}
                                    {slide.images && slide.images.map((img, idx) => (
                                        <div key={idx} className="flex justify-center my-2">
                                            <img
                                                src={`data:${img.content_type};base64,${img.content}`}
                                                alt={`Slide ${currentSlide + 1} Image ${idx}`}
                                                className="max-h-[40vh] object-contain rounded-lg shadow-sm border border-neutral-200"
                                            />
                                        </div>
                                    ))}

                                    {/* Texts */}
                                    <div className="space-y-4">
                                        {slide.texts && slide.texts.map((text, idx) => (
                                            <p key={idx} className="text-base md:text-lg text-neutral-text-main leading-snug font-medium whitespace-pre-wrap break-words border-l-4 border-blue-100 pl-4 py-1 bg-white/50 rounded-r-lg shadow-sm">
                                                {text}
                                            </p>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Navigation Overlays */}
                            <button
                                onClick={() => setCurrentSlide(prev => Math.max(0, prev - 1))}
                                disabled={currentSlide === 0}
                                className={`absolute left-4 top-1/2 -translate-y-1/2 p-4 rounded-full bg-black/10 hover:bg-black/20 text-black transition-all ${currentSlide === 0 ? 'opacity-0' : 'opacity-100'}`}
                            >
                                <FaChevronLeft size={24} />
                            </button>
                            <button
                                onClick={() => setCurrentSlide(prev => Math.min(slides.length - 1, prev + 1))}
                                disabled={currentSlide === slides.length - 1}
                                className={`absolute right-4 top-1/2 -translate-y-1/2 p-4 rounded-full bg-black/10 hover:bg-black/20 text-black transition-all ${currentSlide === slides.length - 1 ? 'opacity-0' : 'opacity-100'}`}
                            >
                                <FaChevronRight size={24} />
                            </button>
                        </div>

                        {/* Slider Controls */}
                        <div className="bg-neutral-800 text-white p-4 flex items-center justify-between">
                            <div className="text-sm font-bold ml-4">
                                Slide {currentSlide + 1} / {slides.length}
                            </div>
                            <div className="flex gap-4">
                                <button
                                    onClick={() => setCurrentSlide(prev => Math.max(0, prev - 1))}
                                    disabled={currentSlide === 0}
                                    className="p-2 hover:bg-white/10 rounded-lg disabled:opacity-30"
                                >
                                    <FaChevronLeft />
                                </button>
                                <button
                                    onClick={() => setCurrentSlide(prev => Math.min(slides.length - 1, prev + 1))}
                                    disabled={currentSlide === slides.length - 1}
                                    className="p-2 hover:bg-white/10 rounded-lg disabled:opacity-30"
                                >
                                    <FaChevronRight />
                                </button>
                            </div>
                            <div className="w-[100px]"></div> {/* Spacer */}
                        </div>
                    </div>
                );

            case 'text':
                return (
                    <div className="w-full flex justify-center py-4 md:py-8 bg-neutral-100/30 min-h-[70vh]">
                        <div className="w-full max-w-[850px] bg-white shadow-2xl rounded-sm border border-neutral-200 relative overflow-hidden">
                            <div className="absolute top-0 left-0 w-full h-1 bg-green-500/20"></div>
                            <div className="px-8 pt-6 pb-2 flex items-center gap-2 border-b border-neutral-100">
                                <FaFileAlt className="text-green-600" />
                                <span className="text-xs font-bold text-neutral-text-tertiary uppercase tracking-widest">純文字檔案</span>
                            </div>
                            <pre className="p-8 md:p-12 text-sm text-neutral-text-main leading-relaxed whitespace-pre-wrap break-words font-mono overflow-auto" style={{ maxHeight: '70vh' }}>
                                {viewData.content as string}
                            </pre>
                            <div className="px-8 py-4 border-t border-neutral-100 flex justify-between items-center text-xs text-neutral-text-tertiary italic">
                                <span>End of File</span>
                                <span>{attachmentTitle}</span>
                            </div>
                        </div>
                    </div>
                );

            case 'image': {
                const imgData = viewData as AttachmentViewResponse & { mime: string };
                return (
                    <div className="w-full flex justify-center items-center py-8 min-h-[70vh] bg-neutral-100/30">
                        <div className="bg-white rounded-2xl shadow-2xl border border-neutral-200 p-6 max-w-4xl w-full flex flex-col items-center gap-4">
                            <div className="flex items-center gap-2 text-neutral-text-tertiary">
                                <FaFileImage className="text-purple-500" />
                                <span className="text-xs font-bold uppercase tracking-widest">圖片預覽</span>
                            </div>
                            <img
                                src={`data:${imgData.mime};base64,${imgData.content}`}
                                alt={attachmentTitle}
                                className="max-w-full max-h-[60vh] object-contain rounded-xl shadow-md border border-neutral-100"
                            />
                            <p className="text-xs text-neutral-text-tertiary">{attachmentTitle}</p>
                        </div>
                    </div>
                );
            }

            case 'download': {
                const dlData = viewData as AttachmentViewResponse & { download_url: string };
                return (
                    <div className="w-full flex justify-center items-center min-h-[70vh]">
                        <div className="bg-white rounded-2xl shadow-xl border border-neutral-200 p-12 max-w-md w-full text-center flex flex-col items-center gap-6">
                            <div className="w-20 h-20 rounded-2xl bg-neutral-50 border border-neutral-200 flex items-center justify-center text-4xl">
                                📄
                            </div>
                            <div>
                                <h3 className="text-lg font-bold text-neutral-text-main mb-1">{attachmentTitle}</h3>
                                <p className="text-sm text-neutral-text-secondary">此格式不支援線上預覽，請下載後開啟</p>
                            </div>
                            <a
                                href={`${API_BASE_URL}${dlData.download_url}`}
                                className="flex items-center gap-2 px-8 py-3 bg-theme-primary text-white rounded-xl font-bold shadow-lg hover:shadow-xl hover:scale-105 active:scale-95 transition-all duration-200"
                            >
                                <FaDownload />
                                下載檔案
                            </a>
                        </div>
                    </div>
                );
            }

            default:
                return (
                    <div className="w-full flex justify-center items-center min-h-[70vh]">
                        <div className="text-neutral-text-tertiary text-center">
                            <p className="text-4xl mb-4">🤔</p>
                            <p>無法預覽此附件</p>
                        </div>
                    </div>
                );
        }
    };


    return (
        <div className="min-h-screen bg-neutral-bg flex flex-col h-screen overflow-hidden">
            {/* Main Content Area */}
            <main id="attachment-layout-row" className="flex-grow flex flex-row w-full relative overflow-hidden">
                {/* Content Area (Left) */}
                <div className="flex-1 overflow-y-auto custom-scrollbar p-6 md:p-8 flex flex-col min-w-0">
                    <div className="max-w-6xl mx-auto w-full mb-10">
                        <h1 className="text-3xl font-bold text-neutral-text-main mb-6">{attachmentTitle}</h1>
                        {renderContent()}
                    </div>

                    {/* Finish Button */}
                    <div className="max-w-6xl mx-auto w-full flex flex-col items-center py-12 gap-3">
                        <button
                            onClick={handleFinish}
                            className="px-12 py-5 bg-theme-primary text-white rounded-2xl font-bold text-xl shadow-xl hover:shadow-2xl hover:scale-105 active:scale-95 transition-all duration-300"
                        >
                            完成閱讀並返回課程
                        </button>
                        <p className="text-sm text-neutral-text-tertiary flex items-center gap-2">
                            系統將自動記錄您的閱讀進度
                            {activeSeconds > 0 && <span className="text-theme-primary font-medium">· 待記錄: {Math.floor(activeSeconds / 60)}分{activeSeconds % 60}秒</span>}
                        </p>
                    </div>
                </div>

                {/* AI Chatbot Sidebar (Right) */}
                {isChatOpen ? (
                    <div
                        className="bg-white flex flex-col shadow-2xl z-20 shrink-0 relative transition-none sticky top-6 rounded-2xl border border-gray-100 m-2 ml-0 overflow-hidden"
                        style={{ width: `${chatWidth}px`, height: typeof sidebarHeight === 'number' ? `${sidebarHeight}px` : sidebarHeight }}
                    >
                        {/* Resize Handle */}
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
                        <div ref={chatHistoryRef} className="flex-grow overflow-y-auto p-3 space-y-3 bg-gray-50/50 min-h-0 custom-scrollbar">
                            {isLoadingChatHistory && (
                                <div className="text-center text-gray-400 text-sm py-2">載入對話紀錄中...</div>
                            )}
                            {chatHistory.map((msg, index) => (
                                <div key={index} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                    <div className={`max-w-[90%] rounded-2xl p-3 shadow-sm ${msg.role === 'user'
                                        ? 'bg-theme-primary text-white rounded-tr-none'
                                        : 'bg-white border border-gray-100 text-neutral-text-main rounded-tl-none'
                                        }`}>
                                        <div className="text-sm leading-relaxed">
                                            {msg.role === 'ai' ? (() => {
                                                const docIdToNum = new Map<string, number>();
                                                let counter = 1;
                                                const processedText = msg.text.replace(/\[doc:(\d+)\]/g, (_: string, id: string) => {
                                                    if (!docIdToNum.has(id)) docIdToNum.set(id, counter++);
                                                    return `[${docIdToNum.get(id)}]`;
                                                });
                                                const hasCitations = docIdToNum.size > 0;
                                                const numberedSources = (msg.sources ?? []).map((s: any, i: number) => ({
                                                    ...s,
                                                    num: hasCitations ? docIdToNum.get(String(s.chunk_id)) ?? null : i + 1,
                                                })).filter((s: any) => s.num !== null).sort((a: any, b: any) => a.num - b.num);
                                                return (
                                                    <>
                                                        <ReactMarkdown
                                                            remarkPlugins={[remarkGfm]}
                                                            components={{
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
                                                                    {numberedSources.map((source: any, idx: number) => (
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
                    // Collapsed Chat Toggle - Floating Icon
                    <button
                        onClick={() => setIsChatOpen(true)}
                        className="absolute right-6 top-6 z-50 w-12 h-12 bg-white text-theme-primary border border-gray-200 rounded-full shadow-lg flex items-center justify-center hover:bg-gray-50 hover:scale-105 transition-all duration-300"
                        title="展開 AI 助手"
                    >
                        <FaRobot size={20} />
                    </button>
                )}


            </main>
        </div>
    );
};

export default AttachmentViewer;
