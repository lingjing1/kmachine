import ReactDOM from 'react-dom';
import { useState, useEffect } from 'react';
import { FaStar, FaExclamationTriangle, FaTimes, FaRobot, FaChevronDown, FaImage } from "react-icons/fa";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Button from '../common/Button';
import Textarea from '../common/Textarea';
import API_BASE_URL from '../../config/api';

const Star = FaStar;
const AlertTriangle = FaExclamationTriangle;

interface ChunkMetadata {
    document_name: string;
    page: number;
    page_range?: number[];
    uploaded_at: string;
    has_images: boolean;
    images?: Array<{
        base64?: string;
        url?: string;
        mime_type: string;
        caption?: string;
        vision_description?: string;
    }>;
    similarity_score: number;
}

interface Chunk {
    chunk_id: number | string;
    text: string;
    source_metadata: ChunkMetadata;
}

export interface ReferenceDrawerProps {
    isOpen: boolean;
    onClose: () => void;
    chunk: Chunk | null;
    evidence?: string;
    matchScore?: number;
    jobId?: number;
    onFeedback?: (chunkId: number | string, rating: number, comment: string, errorTypes: string[]) => Promise<void>;
    inline?: boolean;
    defaultWidthRatio?: number;
}

const ERROR_CATEGORIES = [
    { id: 'wrong_chunk', label: '引用錯誤 (非相關段落)' },
    { id: 'incomplete', label: '引用不完整 (遺漏關鍵訊息)' },
    { id: 'over_citation', label: '過度引用 (包含無關雜訊)' },
    { id: 'hallucination', label: '幻覺內容 (原文無此資訊)' }
];

export function ReferencePanel(props: ReferenceDrawerProps) {
    const {
        chunk,
        matchScore,
        onFeedback,
        onClose
    } = props;
    const [rating, setRating] = useState(0);
    const [comment, setComment] = useState("");
    const [selectedErrors, setSelectedErrors] = useState<string[]>([]);

    const getPageDisplay = () => {
        if (!chunk) return '';
        const { page, page_range } = chunk.source_metadata;
        if (page_range && page_range.length > 0) {
            const start = Math.min(...page_range);
            const end = Math.max(...page_range);
            if (start !== end) return `P.${start}-${end}`;
            return `P.${start}`;
        }
        return `P.${page}`;
    };

    const renderContentWithImages = () => {
        if (!chunk) return null;

        const renderImageCard = (img: any, index: number) => {
            return (
                <div key={`img-card-${index}`} className="my-6 border border-gray-200 rounded-lg overflow-hidden bg-gray-50">
                    {/* Image Header */}
                    <div className="px-3 py-2 bg-gray-100 border-b border-gray-200 flex items-center gap-2 text-xs font-semibold text-gray-600">
                        <FaImage className="text-purple-500" />
                        圖片內容
                    </div>

                    <div className="p-4 flex flex-col items-center bg-gray-50/50">
                        <img
                            src={img.url ? (img.url.startsWith('http') ? img.url : `${API_BASE_URL}${img.url}`) : img.base64}
                            alt={img.caption || "引用圖片"}
                            className="max-h-96 object-contain rounded shadow-sm border border-gray-100"
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
                            {img.vision_description ? (
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
                                        {img.vision_description}
                                    </ReactMarkdown>
                                </div>
                            ) : (
                                "尚無 AI 圖片解析說明"
                            )}
                        </div>
                    </details>
                </div>
            );
        };

        // 1. Structured Content - Best for layout fidelity
        // Need to cast chunk as any because strict TS might not see the new property yet if interface update failed partially
        if ((chunk as any).structured_content && (chunk as any).structured_content.length > 0) {
            return (
                <div className="space-y-4">
                    {(chunk as any).structured_content.map((item: any, idx: number) => {
                        if (item.type === 'image') {
                            // Try to enrich image data from metadata if available
                            const imgMeta = chunk.source_metadata.images?.find((img: any) =>
                                (img.url && item.image_path && img.url.includes(item.image_path)) ||
                                (img.url === item.url)
                            );

                            const displayImg = {
                                ...item,
                                ...imgMeta,
                                url: item.image_path ? `/uploads/${item.image_path}` : (item.url || (imgMeta ? imgMeta.url : '')),
                                vision_description: item.vision_description || (imgMeta ? imgMeta.vision_description : '')
                            };
                            return renderImageCard(displayImg, idx);
                        } else {
                            // Text content
                            return (
                                <div key={idx} className="prose prose-sm max-w-none text-gray-600 leading-relaxed mb-4 whitespace-pre-wrap font-newsreader">
                                    {item.content}
                                </div>
                            );
                        }
                    })}
                </div>
            );
        }

        // 2. Legacy/Fallback - Split by VLM tags
        const parts = chunk.text.split(/(<圖片描述>[\s\S]*?<\/圖片描述>)/g);
        const images = chunk.source_metadata.images || [];
        let imgIndex = 0;

        const contentElements = parts.map((part, index) => {
            // Check if this part is an image VLM block
            if (part.startsWith('<圖片描述>')) {
                const currentImgIndex = imgIndex;
                const img = images[currentImgIndex];

                // Increment index for the next image block
                imgIndex++;

                if (img) {
                    return renderImageCard(img, currentImgIndex);
                }
                return null;
            } else {
                // Normal text block
                let cleanPart = part.replace(/<\/?圖片描述>/g, '').trim();
                if (!cleanPart) return null;

                return (
                    <div key={`text-${index}`} className="prose prose-sm max-w-none text-gray-600 leading-relaxed mb-4 whitespace-pre-wrap font-newsreader">
                        {cleanPart}
                    </div>
                );
            }
        });

        return (
            <>
                {contentElements}
            </>
        );
    };

    if (!chunk) return null;

    const handleSubmit = async () => {
        if (rating === 0) {
            alert("請先給予評分");
            // throw new Error("Rating required"); // Removed throw to avoid unhandled rejection in UI
            return;
        }

        if (onFeedback) {
            await onFeedback(chunk.chunk_id, rating, comment, selectedErrors);
        }

        // Wait a bit to show success state before closing
        setTimeout(() => {
            onClose();
            // Reset state
            setRating(0);
            setComment("");
            setSelectedErrors([]);
        }, 1000);
    };

    const toggleError = (errorId: string) => {
        setSelectedErrors(prev =>
            prev.includes(errorId)
                ? prev.filter(id => id !== errorId)
                : [...prev, errorId]
        );
    };

    return (
        <div className="space-y-6">
            {/* 1. Header Info Section */}
            <div className="flex flex-col gap-3 border-b border-gray-100 pb-4">
                <div className="flex items-center justify-between">
                    <span className="font-semibold text-lg text-gray-800 break-all leading-snug">{chunk.source_metadata.document_name}</span>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                    <span className="bg-gray-100 text-gray-600 px-2.5 py-1 rounded-md font-medium whitespace-nowrap">
                        {getPageDisplay()}
                    </span>
                    {matchScore !== undefined && (
                        <div className={`flex flex-shrink-0 items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${matchScore >= 80 ? 'bg-green-50 text-green-700 border-green-200' :
                            matchScore >= 60 ? 'bg-yellow-50 text-yellow-700 border-yellow-200' :
                                'bg-red-50 text-red-700 border-red-200'
                            }`}>
                            <span>{Math.round(matchScore)}% Match</span>
                        </div>
                    )}
                </div>
            </div>

            {/* 3. Main Text Content with Inline Images */}
            <div>
                {/* Header Removed */}
                <div>
                    {renderContentWithImages()}
                </div>
            </div>

            {/* 教師反饋區 */}
            <div className="pt-6 border-t border-gray-200">
                <h3 className="font-semibold text-lg mb-4 flex items-center gap-2">
                    💬 檢索準確度回饋
                    <span className="text-xs font-normal text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                        幫助我們優化搜尋引擎
                    </span>
                </h3>

                <div className="space-y-4">
                    {/* Star Rating */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            此段落是否符合您的搜尋意圖？
                        </label>
                        <div className="flex items-center gap-2">
                            {[1, 2, 3, 4, 5].map((star) => (
                                <button
                                    key={star}
                                    onClick={() => setRating(star)}
                                    className="transition-transform hover:scale-110 focus:outline-none"
                                >
                                    <Star
                                        className={`w-8 h-8 transition-colors ${star <= rating
                                            ? "fill-yellow-400 text-yellow-400"
                                            : "text-gray-300 hover:text-yellow-200"
                                            }`}
                                    />
                                </button>
                            ))}
                            <span className="ml-3 text-sm font-medium text-gray-600">
                                {rating === 1 && "非常不相關"}
                                {rating === 2 && "不太相關"}
                                {rating === 3 && "普通"}
                                {rating === 4 && "相關"}
                                {rating === 5 && "精準"}
                            </span>
                        </div>
                    </div>

                    {/* Error Categories (Only show if rating <= 3) */}
                    {rating > 0 && rating <= 3 && (
                        <div className="animate-in fade-in slide-in-from-top-2 duration-300">
                            <label className="block text-sm font-medium text-red-600 mb-2 flex items-center gap-1">
                                <AlertTriangle className="w-4 h-4" />
                                主要問題是什麼？(可複選)
                            </label>
                            <div className="grid grid-cols-1 gap-2">
                                {ERROR_CATEGORIES.map((cat) => (
                                    <button
                                        key={cat.id}
                                        onClick={() => toggleError(cat.id)}
                                        className={`text-left px-3 py-2 rounded-md border text-sm transition-all ${selectedErrors.includes(cat.id)
                                            ? "bg-red-50 border-red-500 text-red-700 shadow-sm"
                                            : "bg-white border-gray-200 text-gray-600 hover:border-red-200"
                                            }`}
                                    >
                                        {cat.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Comment */}
                    <div>
                        <Textarea
                            label="詳細說明 (選填)"
                            value={comment}
                            onChange={(e) => setComment(e.target.value)}
                            placeholder="例如：這段文字主要是在講 B，但我搜尋的是 A..."
                            className="min-h-[80px]"
                        />
                    </div>

                    {/* Footer Actions */}
                    <div className="flex justify-end gap-3 pt-2">
                        <Button variant="ghost" onClick={onClose} idleText="取消" />
                        <Button
                            onClick={handleSubmit}
                            disabled={rating === 0}
                            idleText="提交回饋"
                            loadingText="提交中..."
                            successText="提交成功"
                            className="bg-blue-600 hover:bg-blue-700 text-white"
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}




export function ReferenceDrawer(props: ReferenceDrawerProps) {
    const { isOpen, onClose /* , inline */, defaultWidthRatio = 0.31 } = props;

    // Resizing State
    const [drawerWidth, setDrawerWidth] = useState(() => {
        const width = window.innerWidth * defaultWidthRatio;
        return Math.min(Math.max(width, 300), 1200); // Constraint
    });
    const [isResizing, setIsResizing] = useState(false);

    // Sync width if default ratio changes or drawer is reopened (useful for HMR or dynamic adjustments)
    useEffect(() => {
        if (isOpen) {
            const width = window.innerWidth * defaultWidthRatio;
            setDrawerWidth(Math.min(Math.max(width, 300), 1200));
        }
    }, [isOpen, defaultWidthRatio]);

    // Prevent body scroll - REMOVED to allow scrolling main content
    // useEffect(() => { ... }, [isOpen]);

    // Resizing Logic
    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            if (!isResizing) return;
            const newWidth = window.innerWidth - e.clientX;
            const minWidth = window.innerWidth * defaultWidthRatio; // Minimum 

            if (newWidth > minWidth && newWidth < 1200) {
                setDrawerWidth(newWidth);
            } else if (newWidth <= minWidth) {
                setDrawerWidth(minWidth);
            }
        };

        const handleMouseUp = () => {
            setIsResizing(false);
            document.body.style.cursor = 'default';
        };

        if (isResizing) {
            document.body.style.cursor = 'ew-resize';
            window.addEventListener('mousemove', handleMouseMove);
            window.addEventListener('mouseup', handleMouseUp);
        }

        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, [isResizing]);

    if (!isOpen) return null;

    return ReactDOM.createPortal(
        <>
            {/* Backdrop Removed to allow interaction with main content */}

            {/* Resizable Drawer Panel */}
            <div
                className="fixed inset-y-0 right-0 z-50 bg-white shadow-2xl flex flex-col transition-width duration-0"
                style={{ width: drawerWidth }}
                role="dialog"
                aria-modal="true"
            >
                {/* Resize Handle */}
                <div
                    className="absolute left-0 top-0 bottom-0 w-1.5 cursor-ew-resize hover:bg-blue-400/50 z-50 transition-colors"
                    onMouseDown={(e) => {
                        e.stopPropagation();
                        setIsResizing(true);
                    }}
                >
                    {/* Visual indicator line */}
                    <div className={`h-full w-[1px] mx-auto bg-gray-200 ${isResizing ? 'bg-blue-400' : ''}`} />
                </div>

                {/* Gradient Header - Matching QuestionMetadataDrawer */}
                <div className="flex-none flex items-center justify-between px-6 py-4 border-b border-blue-100 bg-gradient-to-r from-blue-50 via-cyan-50 to-blue-50">
                    <h3 className="text-lg font-bold bg-gradient-to-r from-blue-700 to-cyan-600 bg-clip-text text-transparent flex items-center gap-2">
                        引用來源詳情
                    </h3>
                    <button
                        onClick={onClose}
                        className="p-1.5 -mr-1 rounded-full text-neutral-icon hover:bg-white/80 hover:text-blue-600 transition-all duration-200 hover:shadow-md"
                    >
                        <FaTimes className="w-4 h-4" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6">
                    <ReferencePanel {...props} />
                </div>
            </div>
        </>,
        document.body
    );
}
