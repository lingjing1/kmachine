// frontend/src/components/common/RichTextEditor.tsx
import React, { useState } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Underline from '@tiptap/extension-underline';
import Link from '@tiptap/extension-link';
import { Color } from '@tiptap/extension-color';
import { TextStyle } from '@tiptap/extension-text-style';
import {
    FaBold, FaItalic, FaUnderline, FaListUl, FaListOl,
    FaLink, FaCode, FaQuoteRight, FaMinus, FaPalette
} from 'react-icons/fa';
import Modal from './Modal';
import Button from './Button';

interface RichTextEditorProps {
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
}

const RichTextEditor: React.FC<RichTextEditorProps> = ({
    value,
    onChange,
    placeholder = '輸入內容...'
}) => {
    const [isLinkModalOpen, setIsLinkModalOpen] = useState(false);
    const [linkUrl, setLinkUrl] = useState('');
    const [showColorPicker, setShowColorPicker] = useState(false);

    const editor = useEditor({
        extensions: [
            StarterKit.configure({
                heading: {
                    levels: [1, 2, 3],
                },
                link: false,      // StarterKit v3 已內建，下方另行註冊以套用自訂設定
                underline: false, // StarterKit v3 已內建，下方另行註冊
            }),
            Underline,
            TextStyle,
            Color,
            Link.configure({
                openOnClick: false,
                HTMLAttributes: {
                    class: 'text-blue-600 underline hover:text-blue-800',
                },
            }),
        ],
        content: value,
        onUpdate: ({ editor }) => {
            const html = editor.getHTML();
            onChange(html);
        },
        editorProps: {
            attributes: {
                class: 'prose prose-sm max-w-none focus:outline-none min-h-[150px] p-4',
            },
        },
    });

    React.useEffect(() => {
        if (editor && value !== editor.getHTML()) {
            editor.commands.setContent(value);
        }
    }, [value, editor]);

    if (!editor) {
        return null;
    }

    const ToolbarButton: React.FC<{
        onClick: () => void;
        isActive?: boolean;
        title: string;
        children: React.ReactNode;
    }> = ({ onClick, isActive, title, children }) => (
        <button
            type="button"
            onClick={onClick}
            className={`p-2 rounded transition-colors ${isActive
                ? 'bg-blue-100 text-blue-700'
                : 'text-neutral-icon hover:bg-neutral-background hover:text-theme-primary'
                }`}
            title={title}
        >
            {children}
        </button>
    );

    const colors = [
        { name: '黑色', value: '#000000' },
        { name: '深灰', value: '#4B5563' },
        { name: '紅色', value: '#EF4444' },
        { name: '橙色', value: '#F97316' },
        { name: '黃色', value: '#EAB308' },
        { name: '綠色', value: '#22C55E' },
        { name: '藍色', value: '#3B82F6' },
        { name: '靛藍', value: '#6366F1' },
        { name: '紫色', value: '#A855F7' },
        { name: '粉色', value: '#EC4899' },
    ];

    const handleAddLink = () => {
        setLinkUrl('');
        setIsLinkModalOpen(true);
    };

    const confirmAddLink = () => {
        if (linkUrl) {
            editor.chain().focus().setLink({ href: linkUrl }).run();
        }
        setIsLinkModalOpen(false);
        setLinkUrl('');
    };

    return (
        <>
            <div className="border border-neutral-border rounded-lg focus-within:ring-2 focus-within:ring-theme-ring focus-within:border-theme-primary transition-all bg-white">
                {/* Toolbar - Made sticky and added rounded-t-lg to replace overflow-hidden clipping */}
                <div className="sticky top-0 z-20 bg-gray-100 border-b border-gray-200 px-3 py-2 flex items-center gap-1 flex-wrap rounded-t-lg">
                    <ToolbarButton
                        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
                        isActive={editor.isActive('heading', { level: 1 })}
                        title="大標題"
                    >
                        <span className="font-bold text-sm">H1</span>
                    </ToolbarButton>

                    <ToolbarButton
                        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
                        isActive={editor.isActive('heading', { level: 2 })}
                        title="中標題"
                    >
                        <span className="font-bold text-sm">H2</span>
                    </ToolbarButton>

                    <ToolbarButton
                        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
                        isActive={editor.isActive('heading', { level: 3 })}
                        title="小標題"
                    >
                        <span className="font-bold text-sm">H3</span>
                    </ToolbarButton>

                    <div className="w-px h-6 bg-neutral-border mx-1" />

                    <ToolbarButton
                        onClick={() => editor.chain().focus().toggleBold().run()}
                        isActive={editor.isActive('bold')}
                        title="粗體"
                    >
                        <FaBold size={14} />
                    </ToolbarButton>

                    <ToolbarButton
                        onClick={() => editor.chain().focus().toggleItalic().run()}
                        isActive={editor.isActive('italic')}
                        title="斜體"
                    >
                        <FaItalic size={14} />
                    </ToolbarButton>

                    <ToolbarButton
                        onClick={() => editor.chain().focus().toggleUnderline().run()}
                        isActive={editor.isActive('underline')}
                        title="底線"
                    >
                        <FaUnderline size={14} />
                    </ToolbarButton>

                    {/* Color Picker */}
                    <div className="relative">
                        <button
                            type="button"
                            onClick={() => setShowColorPicker(!showColorPicker)}
                            className="p-2 rounded text-neutral-icon hover:bg-neutral-background hover:text-theme-primary transition-colors"
                            title="文字顏色"
                        >
                            <FaPalette size={14} />
                        </button>
                        {showColorPicker && (
                            <div className="absolute left-0 top-full mt-1 bg-white border border-neutral-border rounded-lg shadow-lg p-3 z-30">
                                <div className="grid grid-cols-5 gap-5">
                                    {colors.map((color) => (
                                        <button
                                            key={color.value}
                                            type="button"
                                            onClick={() => {
                                                editor.chain().focus().setColor(color.value).run();
                                                setShowColorPicker(false);
                                            }}
                                            className="w-7 h-7 rounded border-2 border-gray-200 hover:border-blue-500 hover:scale-110 transition-all"
                                            style={{ backgroundColor: color.value }}
                                            title={color.name}
                                        />
                                    ))}
                                </div>
                                <button
                                    type="button"
                                    onClick={() => {
                                        editor.chain().focus().unsetColor().run();
                                        setShowColorPicker(false);
                                    }}
                                    className="w-full mt-2 pt-2 border-t border-neutral-border text-xs text-neutral-text-secondary hover:text-neutral-text-main py-1"
                                >
                                    清除顏色
                                </button>
                            </div>
                        )}
                    </div>

                    <div className="w-px h-6 bg-neutral-border mx-1" />

                    <ToolbarButton
                        onClick={() => editor.chain().focus().toggleBulletList().run()}
                        isActive={editor.isActive('bulletList')}
                        title="無序列表"
                    >
                        <FaListUl size={14} />
                    </ToolbarButton>

                    <ToolbarButton
                        onClick={() => editor.chain().focus().toggleOrderedList().run()}
                        isActive={editor.isActive('orderedList')}
                        title="有序列表"
                    >
                        <FaListOl size={14} />
                    </ToolbarButton>

                    <div className="w-px h-6 bg-neutral-border mx-1" />

                    <ToolbarButton
                        onClick={handleAddLink}
                        isActive={editor.isActive('link')}
                        title="連結"
                    >
                        <FaLink size={14} />
                    </ToolbarButton>

                    <ToolbarButton
                        onClick={() => editor.chain().focus().toggleCode().run()}
                        isActive={editor.isActive('code')}
                        title="程式碼"
                    >
                        <FaCode size={14} />
                    </ToolbarButton>

                    <ToolbarButton
                        onClick={() => editor.chain().focus().toggleBlockquote().run()}
                        isActive={editor.isActive('blockquote')}
                        title="引用"
                    >
                        <FaQuoteRight size={14} />
                    </ToolbarButton>

                    <ToolbarButton
                        onClick={() => editor.chain().focus().setHorizontalRule().run()}
                        title="分隔線"
                    >
                        <FaMinus size={14} />
                    </ToolbarButton>
                </div>

                {/* Editor Content */}
                <EditorContent
                    editor={editor}
                    placeholder={placeholder}
                />
            </div>

            {/* Link Modal */}
            <Modal
                isOpen={isLinkModalOpen}
                onClose={() => setIsLinkModalOpen(false)}
                title="新增連結"
            >
                <div className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-neutral-text-main mb-1">網址</label>
                        <input
                            type="url"
                            value={linkUrl}
                            onChange={(e) => setLinkUrl(e.target.value)}
                            className="w-full px-4 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-theme-ring focus:border-theme-primary"
                            placeholder="https://example.com"
                            autoFocus
                        />
                    </div>
                    <div className="flex justify-end gap-3 pt-2">
                        <Button
                            variant="secondary"
                            onClick={() => setIsLinkModalOpen(false)}
                            idleText="取消"
                        />
                        <Button
                            variant="primary"
                            onClick={confirmAddLink}
                            idleText="確定"
                            disabled={!linkUrl.trim()}
                        />
                    </div>
                </div>
            </Modal>
        </>
    );
};

export default RichTextEditor;
