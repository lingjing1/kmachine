// frontend/src/components/common/MarkdownEditor.tsx
import React, { useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import {
    FaBold, FaItalic, FaListUl, FaListOl, FaLink, FaCode, FaQuoteRight, FaMinus
} from 'react-icons/fa';

interface MarkdownEditorProps {
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    rows?: number;
    showPreview?: boolean;
}

const MarkdownEditor: React.FC<MarkdownEditorProps> = ({
    value,
    onChange,
    placeholder = '輸入內容...',
    rows = 6,
    showPreview = true
}) => {
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const insertMarkdown = (before: string, after: string = '', newLine: boolean = false) => {
        const textarea = textareaRef.current;
        if (!textarea) return;

        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const selectedText = value.substring(start, end);

        let beforeText = before;
        let afterText = after;

        // For new line insertions, add line breaks if needed
        if (newLine) {
            const beforeSelection = value.substring(0, start);
            const afterSelection = value.substring(end);
            const needsNewLineBefore = beforeSelection.length > 0 && !beforeSelection.endsWith('\n');
            const needsNewLineAfter = afterSelection.length > 0 && !afterSelection.startsWith('\n');

            beforeText = (needsNewLineBefore ? '\n' : '') + before;
            afterText = after + (needsNewLineAfter ? '\n' : '');
        }

        const newText = value.substring(0, start) + beforeText + selectedText + afterText + value.substring(end);

        onChange(newText);

        // Set cursor position after insertion
        setTimeout(() => {
            textarea.focus();
            const newCursorPos = start + beforeText.length + selectedText.length;
            textarea.setSelectionRange(newCursorPos, newCursorPos);
        }, 0);
    };

    const toolbarButtons = [
        { icon: () => <span className="font-bold text-sm">H1</span>, label: '大標題', action: () => insertMarkdown('# ', '', true) },
        { icon: () => <span className="font-bold text-sm">H2</span>, label: '中標題', action: () => insertMarkdown('## ', '', true) },
        { icon: () => <span className="font-bold text-sm">H3</span>, label: '小標題', action: () => insertMarkdown('### ', '', true) },
        { icon: FaBold, label: '粗體', action: () => insertMarkdown('**', '**') },
        { icon: FaItalic, label: '斜體', action: () => insertMarkdown('*', '*') },
        { icon: FaListUl, label: '無序列表', action: () => insertMarkdown('- ', '', true) },
        { icon: FaListOl, label: '有序列表', action: () => insertMarkdown('1. ', '', true) },
        { icon: FaLink, label: '連結', action: () => insertMarkdown('[', '](url)') },
        { icon: FaCode, label: '程式碼', action: () => insertMarkdown('`', '`') },
        { icon: FaQuoteRight, label: '引用', action: () => insertMarkdown('> ', '', true) },
        { icon: FaMinus, label: '分隔線', action: () => insertMarkdown('---', '', true) },
    ];

    return (
        <div className="space-y-2">
            <div className="border border-neutral-border rounded-lg overflow-hidden focus-within:ring-2 focus-within:ring-theme-ring focus-within:border-theme-primary transition-all">
                {/* Toolbar */}
                <div className="bg-neutral-background border-b border-neutral-border px-3 py-2 flex items-center gap-1 flex-wrap">
                    {toolbarButtons.map((button, index) => (
                        <button
                            key={index}
                            type="button"
                            onClick={button.action}
                            className="p-2 rounded hover:bg-white hover:text-theme-primary text-neutral-icon transition-colors"
                            title={button.label}
                        >
                            <button.icon size={14} />
                        </button>
                    ))}
                </div>

                {/* Textarea */}
                <textarea
                    ref={textareaRef}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder={placeholder}
                    rows={rows}
                    className="w-full px-4 py-3 focus:outline-none resize-none font-mono text-sm"
                />
            </div>

            {/* Live Preview */}
            {showPreview && value && (
                <div className="border border-neutral-border rounded-lg p-4 bg-neutral-background/30">
                    <div className="text-xs font-medium text-neutral-text-tertiary mb-2">即時預覽</div>
                    <div className="prose prose-sm max-w-none announcement-content text-neutral-text-main">
                        <ReactMarkdown>{value}</ReactMarkdown>
                    </div>
                </div>
            )}
        </div>
    );
};

export default MarkdownEditor;
