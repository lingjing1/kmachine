import React, { useState } from 'react';
import { FaTimes, FaQuestionCircle, FaLightbulb } from 'react-icons/fa';
import ReactMarkdown from 'react-markdown';

interface SummaryListItemProps {
    item: string;
    idx: number;
    sectionIdx: number;
    isEditing: boolean;
    onContentChange: (sectionIdx: number, contentIdx: number, newText: string) => void;
    onDeleteContent: (sectionIdx: number, contentIdx: number) => void;
}

export const SummaryListItem: React.FC<SummaryListItemProps> = ({
    item,
    idx,
    sectionIdx,
    isEditing,
    onContentChange,
    onDeleteContent
}) => {
    // State for toggling Q&A answer visibility
    const [isOpen, setIsOpen] = useState(false);

    if (isEditing) {
        return (
            <div className="flex items-start gap-2 transition-colors group">
                <div className="flex-1 flex items-start gap-2">
                    <span className="text-gray-400 mt-2">•</span>
                    <textarea
                        value={item}
                        onChange={(e) => onContentChange(sectionIdx, idx, e.target.value)}
                        className="flex-1 border border-gray-300 rounded px-2 py-1 text-neutral-text-secondary leading-relaxed focus:border-theme-primary outline-none resize-none"
                        rows={2}
                        placeholder="內容要點... (使用 '|||' 分隔問題與答案)"
                    />
                    <button
                        onClick={() => onDeleteContent(sectionIdx, idx)}
                        className="mt-2 text-gray-400 hover:text-red-600 transition-colors"
                        title="刪除要點"
                    >
                        <FaTimes size={12} />
                    </button>
                </div>
            </div>
        );
    }

    const trimmedItem = item.trim();

    // Check for "Question ||| Answer" format
    if (trimmedItem.includes('|||')) {
        const [question, answer] = trimmedItem.split('|||').map(s => s.trim());

        // Remove markdown list markers from question if present (e.g. "1. Q: ...")
        const cleanQuestion = question.replace(/^(\d+\.|[-*])\s+/, '').trim();

        return (
            <div className="border border-gray-100 rounded-lg bg-gray-50/50 mb-2 overflow-hidden">
                <button
                    onClick={() => setIsOpen(!isOpen)}
                    className="w-full flex items-start gap-3 p-3 text-left hover:bg-gray-100/80 transition-colors"
                >
                    <div className="mt-1 flex-shrink-0">
                        <span className={`flex items-center justify-center w-5 h-5 rounded-full ${isOpen
                            ? 'bg-amber-100 text-amber-600'
                            : 'bg-blue-100 text-blue-600'
                            }`}>
                            {isOpen ? <FaLightbulb size={12} /> : <FaQuestionCircle size={12} />}
                        </span>
                    </div>
                    <span className="font-bold text-neutral-text-main leading-relaxed markdown-content">
                        <ReactMarkdown components={{ p: ({ node, ...props }) => <p className="mt-0 mb-0" {...props} /> }}>
                            {cleanQuestion}
                        </ReactMarkdown>
                    </span>
                </button>

                {isOpen && (
                    <div className="px-4 pb-4 pt-0 pl-11">
                        <div className="pt-2 border-t border-gray-200/60 text-neutral-text-secondary leading-relaxed animate-in fade-in slide-in-from-top-1 duration-200 markdown-content">
                            <ReactMarkdown components={{ p: ({ node, ...props }) => <p className="mt-0 mb-3 last:mb-0" {...props} /> }}>
                                {answer}
                            </ReactMarkdown>
                        </div>
                    </div>
                )}
            </div>
        );
    }

    // Normal list item rendering
    const unorderedMatch = trimmedItem.match(/^[-*]\s+(.+)$/);
    const orderedMatch = trimmedItem.match(/^(\d+)\.\s+(.+)$/);

    let displayContent = trimmedItem;
    let listMarker = null;

    if (unorderedMatch) {
        displayContent = unorderedMatch[1];
        listMarker = (
            <span className="flex-shrink-0 transition-all text-blue-400 group-hover:text-blue-500 leading-relaxed">•</span>
        );
    } else if (orderedMatch) {
        displayContent = orderedMatch[2];
        listMarker = (
            <span className="flex-shrink-0 font-medium min-w-[1.5rem] transition-all text-blue-500 group-hover:text-blue-600 leading-relaxed">{orderedMatch[1]}.</span>
        );
    }

    return (
        <div className="flex items-baseline gap-2 transition-colors group">
            {listMarker}
            <div className={`${listMarker ? 'flex-1' : ''} text-neutral-text-secondary leading-relaxed markdown-content`}>
                <ReactMarkdown components={{ p: ({ node, ...props }) => <span className="block" {...props} /> }}>
                    {displayContent}
                </ReactMarkdown>
            </div>
        </div>
    );
};
