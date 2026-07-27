// frontend/src/components/teacher/PrepGuide.tsx
import { useState } from 'react';
import {
    FaRoute,
    FaChevronDown,
    FaChevronRight,
    FaCloudUploadAlt,
    FaSlidersH,
    FaRegCheckSquare,
    FaClipboardCheck,
    FaRobot,
    FaLink,
    FaStar,
    FaFilePdf,
    FaListUl,
    FaSitemap,
    FaMagic,
    FaMousePointer,
} from 'react-icons/fa';

const STORAGE_KEY = 'cookteaching_guide_collapsed';

interface SubPoint {
    icon: React.ReactNode;
    label: string;
}

interface Step {
    n: number;
    icon: React.ReactNode;
    title: string;
    desc: string;
    highlight?: boolean;
    subs: SubPoint[];
}

const STEPS: Step[] = [
    {
        n: 1,
        icon: <FaCloudUploadAlt size={18} />,
        title: '上傳教材',
        desc: '提供參考資料，系統自動解析內容。',
        subs: [{ icon: <FaFilePdf size={12} />, label: '支援 PDF/投影片等各種格式的檔案，連圖表都能解析' }],
    },
    {
        n: 2,
        icon: <FaSlidersH size={18} />,
        title: '設定生成需求',
        desc: '告訴 AI 想要生成什麼樣的教材。',
        subs: [{ icon: <FaListUl size={12} />, label: '教材類型、詳盡程度、生成指令一次設定' }],
    },
    {
        n: 3,
        icon: <FaRegCheckSquare size={18} />,
        title: '勾選知識點',
        desc: '由你決定教學範疇，AI 只圍繞你勾選的知識點生成。',
        highlight: true,
        subs: [{ icon: <FaSitemap size={12} />, label: '從知識地圖勾選，或自行新增知識點' }],
    },
    {
        n: 4,
        icon: <FaClipboardCheck size={18} />,
        title: '審視生成結果',
        desc: '教材的最終裁量權在你手上。',
        subs: [
            { icon: <FaRobot size={12} />, label: 'LLM 自動評估供參考：品質與事實雙軌訊號' },
            { icon: <FaLink size={12} />, label: '證據對照：每段可溯源至原文，可採納或重新生成' },
        ],
    },
];

function PrepGuide() {
    const [collapsed, setCollapsed] = useState<boolean>(
        () => localStorage.getItem(STORAGE_KEY) === '1'
    );

    const toggle = () => {
        setCollapsed((prev) => {
            const next = !prev;
            localStorage.setItem(STORAGE_KEY, next ? '1' : '0');
            return next;
        });
    };

    return (
        <div className="rounded-2xl border border-theme-border shadow-sm overflow-hidden bg-white">
            {/* Header (always visible) */}
            <button
                type="button"
                onClick={toggle}
                className="w-full flex items-center justify-between gap-4 px-5 py-3.5 text-left bg-gradient-to-r from-theme-gradient-start via-theme-primary to-theme-accent text-white transition-opacity hover:opacity-95"
            >
                <div className="flex items-center gap-3 min-w-0">
                    <div className="flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-full bg-white/20">
                        <FaRoute size={18} />
                    </div>
                    <div className="min-w-0">
                        <h2 className="text-base font-bold leading-tight text-white">
                            備課引導 · 四步把你的教學意圖變成教材
                        </h2>
                        <p className="text-xs text-white/85 leading-tight mt-0.5 truncate">
                            不是一堆零散工具，而是一條由你的教學意圖定錨的引導式備課流程
                        </p>
                    </div>
                </div>
                <span className="flex-shrink-0 inline-flex items-center gap-1.5 rounded-full bg-white/15 hover:bg-white/25 px-3 py-1.5 text-xs font-medium transition-colors">
                    {collapsed ? '展開' : '收合'}
                    <FaChevronDown
                        size={11}
                        className={`transition-transform duration-300 ${collapsed ? '-rotate-90' : 'rotate-0'}`}
                    />
                </span>
            </button>

            {/* Body (collapsible) */}
            <div
                className={`grid transition-[grid-template-rows] duration-300 ease-in-out ${
                    collapsed ? 'grid-rows-[0fr]' : 'grid-rows-[1fr]'
                }`}
            >
                <div className="overflow-hidden">
                    <div className="p-5">
                        {/* Entry-point hint：where to click to start */}
                        <div className="mb-4 flex items-start gap-2.5 px-1">
                            <span className="flex-shrink-0 mt-0.5 text-theme-primary">
                                <FaMousePointer size={14} />
                            </span>
                            <p className="text-xs text-neutral-text-secondary leading-relaxed">
                                <span className="font-semibold text-theme-primary-active">從這裡開始：</span>
                                移至下方「課程內容」→ 選擇週次 → 點教材或試卷的
                                <span className="inline-flex items-center gap-1 mx-1 align-middle rounded-md bg-theme-primary px-1.5 py-0.5 text-[11px] font-medium text-white">
                                    <FaMagic size={10} />
                                    AI 生成
                                </span>
                                按鈕，即可進入以下四步流程。
                            </p>
                        </div>

                        {/* Four-step flow */}
                        <div className="flex flex-col lg:flex-row lg:items-stretch gap-3">
                            {STEPS.map((step, idx) => (
                                <div key={step.n} className="contents lg:flex lg:flex-1 lg:items-stretch">
                                    <StepCard step={step} />
                                    {idx < STEPS.length - 1 && (
                                        <div className="flex items-center justify-center lg:px-1 text-theme-primary/50">
                                            <FaChevronDown size={16} className="lg:hidden" />
                                            <FaChevronRight size={16} className="hidden lg:block" />
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function StepCard({ step }: { step: Step }) {
    return (
        <div
            className={`relative flex-1 rounded-xl border p-4 transition-shadow hover:shadow-md ${
                step.highlight
                    ? 'border-theme-accent ring-1 ring-theme-accent bg-theme-accent-light/40'
                    : 'border-neutral-border bg-theme-surface-hover/60'
            }`}
        >
            {step.highlight && (
                <span className="absolute -top-2 right-3 inline-flex items-center gap-1 rounded-full bg-theme-accent px-2 py-0.5 text-[10px] font-semibold text-white shadow-sm">
                    <FaStar size={9} />
                    你做主
                </span>
            )}
            <div className="flex items-center gap-2.5 mb-2">
                <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-theme-primary to-theme-accent text-white text-sm font-bold">
                    {step.n}
                </div>
                <div className="flex items-center gap-1.5 text-neutral-text-main">
                    <span className="text-theme-primary">{step.icon}</span>
                    <h3 className="text-base font-semibold">{step.title}</h3>
                </div>
            </div>
            <p className="text-sm text-neutral-text-secondary leading-relaxed">{step.desc}</p>
            <ul className="mt-2.5 space-y-1.5 border-t border-neutral-border/70 pt-2.5">
                {step.subs.map((sub, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-neutral-text-secondary leading-relaxed">
                        <span className="flex-shrink-0 mt-0.5 text-theme-accent">{sub.icon}</span>
                        <span>{sub.label}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

export default PrepGuide;
