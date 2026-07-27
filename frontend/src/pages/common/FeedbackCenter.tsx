import { useState, useEffect, useRef } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import {
    FaPaperPlane,
    FaArrowLeft,
    FaChevronDown,
    FaChevronUp,
    FaSearch,
    FaTimes,
    FaUserShield,
    FaBookOpen,
    FaMagic,
    FaLightbulb,
    FaLayerGroup,
    FaClipboardList,
    FaLink,
    FaChartBar,
    FaCommentDots,
} from 'react-icons/fa';
import { MdOutlineFeedback } from 'react-icons/md';
import { getFeedbackConfig, submitFeedbackReport, FAQItem, ProblemType } from '../../services/feedbackApi';
import Spinner from '../../components/common/Spinner';
import Toast from '../../components/common/Toast';
import Footer from '../../components/common/Footer';

// Category metadata: icon, color scheme
const CATEGORY_META: Record<string, { icon: React.ReactNode; color: string; bg: string; border: string; activeBg: string; activeText: string }> = {
    '帳號與權限': {
        icon: <FaUserShield size={14} />,
        color: 'text-violet-600',
        bg: 'bg-violet-50',
        border: 'border-violet-200',
        activeBg: 'bg-violet-600',
        activeText: 'text-white',
    },
    '課程管理': {
        icon: <FaBookOpen size={14} />,
        color: 'text-sky-600',
        bg: 'bg-sky-50',
        border: 'border-sky-200',
        activeBg: 'bg-sky-600',
        activeText: 'text-white',
    },
    'AI 生成與內容解析': {
        icon: <FaMagic size={14} />,
        color: 'text-blue-600',
        bg: 'bg-blue-50',
        border: 'border-blue-200',
        activeBg: 'bg-blue-600',
        activeText: 'text-white',
    },
    '知識點功能': {
        icon: <FaLightbulb size={14} />,
        color: 'text-amber-600',
        bg: 'bg-amber-50',
        border: 'border-amber-200',
        activeBg: 'bg-amber-500',
        activeText: 'text-white',
    },
    '教材與題庫管理': {
        icon: <FaLayerGroup size={14} />,
        color: 'text-emerald-600',
        bg: 'bg-emerald-50',
        border: 'border-emerald-200',
        activeBg: 'bg-emerald-600',
        activeText: 'text-white',
    },
    '試卷編輯與計分': {
        icon: <FaClipboardList size={14} />,
        color: 'text-orange-600',
        bg: 'bg-orange-50',
        border: 'border-orange-200',
        activeBg: 'bg-orange-500',
        activeText: 'text-white',
    },
    'RAG 引用來源與品質校對': {
        icon: <FaLink size={14} />,
        color: 'text-teal-600',
        bg: 'bg-teal-50',
        border: 'border-teal-200',
        activeBg: 'bg-teal-600',
        activeText: 'text-white',
    },
    '學情監控': {
        icon: <FaChartBar size={14} />,
        color: 'text-rose-600',
        bg: 'bg-rose-50',
        border: 'border-rose-200',
        activeBg: 'bg-rose-600',
        activeText: 'text-white',
    },
    '問題回饋': {
        icon: <FaCommentDots size={14} />,
        color: 'text-indigo-600',
        bg: 'bg-indigo-50',
        border: 'border-indigo-200',
        activeBg: 'bg-indigo-600',
        activeText: 'text-white',
    },
};

const DEFAULT_META = {
    icon: <FaCommentDots size={14} />,
    color: 'text-slate-600',
    bg: 'bg-slate-50',
    border: 'border-slate-200',
    activeBg: 'bg-slate-600',
    activeText: 'text-white',
};

const ALL_CATEGORY = '全部';

const FeedbackCenter = () => {
    const navigate = useNavigate();
    const { setHeaderActions } = useOutletContext<any>();
    const [faqs, setFaqs] = useState<FAQItem[]>([]);
    const [problemTypes, setProblemTypes] = useState<ProblemType[]>([]);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [selectedProblems, setSelectedProblems] = useState<string[]>([]);
    const [description, setDescription] = useState('');
    const [openProblemCategories, setOpenProblemCategories] = useState<string[]>([]);

    // FAQ state
    const [selectedCategory, setSelectedCategory] = useState<string>(ALL_CATEGORY);
    const [searchQuery, setSearchQuery] = useState('');
    const [openFaqIds, setOpenFaqIds] = useState<Set<number>>(new Set());
    const [categoryDropdownOpen, setCategoryDropdownOpen] = useState(false);
    const searchInputRef = useRef<HTMLInputElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    const [toast, setToast] = useState<{ show: boolean; message: string; type: 'success' | 'error' }>({
        show: false,
        message: '',
        type: 'success',
    });

    useEffect(() => {
        const fetchConfig = async () => {
            try {
                const config = await getFeedbackConfig();
                setFaqs(config.faqs);
                setProblemTypes(config.problem_types);

                const probCats = Array.from(new Set(config.problem_types.map(p => p.category)));
                if (probCats.length > 0) setOpenProblemCategories([probCats[0]]);
            } catch (err) {
                setToast({
                    show: true,
                    message: '無法載入配置，請稍後再試。',
                    type: 'error',
                });
            } finally {
                setLoading(false);
            }
        };
        fetchConfig();
    }, []);

    // Set Header Actions
    useEffect(() => {
        if (setHeaderActions) {
            setHeaderActions(
                <button
                    onClick={() => navigate(-1)}
                    className="
                            flex items-center gap-2 text-neutral-text-secondary font-medium
                            transition-all duration-200 hover:text-blue-700 group
                        "
                    title="回到課程"
                >
                    <div className="w-10 h-10 rounded-xl bg-white border border-gray-200 shadow-sm flex items-center justify-center transition-all duration-200 group-hover:bg-blue-50 group-hover:border-blue-200">
                        <FaArrowLeft className="w-5 h-5 flex-shrink-0 group-hover:scale-110 transition-transform" />
                    </div>
                    <span className="max-lg:hidden whitespace-nowrap">回到課程</span>
                </button>
            );
        }
        return () => {
            if (setHeaderActions) setHeaderActions(null);
        };
    }, [setHeaderActions, navigate]);

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
                setCategoryDropdownOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Derived: all FAQ categories in order
    const faqCategories = [ALL_CATEGORY, ...Array.from(new Set(faqs.map(f => f.category)))];

    // Derived: filtered FAQ list
    const filteredFaqs = faqs.filter(faq => {
        const matchesCategory = selectedCategory === ALL_CATEGORY || faq.category === selectedCategory;
        const query = searchQuery.trim().toLowerCase();
        const matchesSearch = !query ||
            faq.question.toLowerCase().includes(query) ||
            faq.answer.toLowerCase().includes(query);
        return matchesCategory && matchesSearch;
    });

    // Count per category (after search filter)
    const countForCategory = (cat: string) => {
        if (cat === ALL_CATEGORY) {
            return faqs.filter(faq => {
                const query = searchQuery.trim().toLowerCase();
                return !query || faq.question.toLowerCase().includes(query) || faq.answer.toLowerCase().includes(query);
            }).length;
        }
        return faqs.filter(faq => {
            const matchesCat = faq.category === cat;
            const query = searchQuery.trim().toLowerCase();
            const matchesSearch = !query || faq.question.toLowerCase().includes(query) || faq.answer.toLowerCase().includes(query);
            return matchesCat && matchesSearch;
        }).length;
    };

    const handleToggleFaq = (id: number) => {
        setOpenFaqIds(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    };

    const handleCategorySelect = (cat: string) => {
        setSelectedCategory(cat);
        setOpenFaqIds(new Set());
    };

    const handleClearSearch = () => {
        setSearchQuery('');
        searchInputRef.current?.focus();
    };

    const handleToggleProblem = (id: string) => {
        setSelectedProblems((prev) =>
            prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
        );
    };

    const toggleProblemCategory = (category: string) => {
        setOpenProblemCategories(prev =>
            prev.includes(category) ? prev.filter(c => c !== category) : [...prev, category]
        );
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!description.trim()) {
            setToast({ show: true, message: '請填寫問題描述', type: 'error' });
            return;
        }

        setSubmitting(true);
        try {
            await submitFeedbackReport({
                selected_problems: selectedProblems.length > 0 ? selectedProblems : null,
                description: description,
            });
            setToast({ show: true, message: '感謝您的回饋！我們將盡快處理。', type: 'success' });
            setSelectedProblems([]);
            setDescription('');
        } catch (err) {
            setToast({ show: true, message: '提交失敗，請檢查網路連線。', type: 'error' });
        } finally {
            setSubmitting(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[400px]">
                <Spinner />
            </div>
        );
    }

    const groupedProblemTypes = problemTypes.reduce((acc, type) => {
        const cat = type.category || '其他';
        if (!acc[cat]) acc[cat] = [];
        acc[cat].push(type);
        return acc;
    }, {} as Record<string, ProblemType[]>);

    const selectedMeta = CATEGORY_META[selectedCategory] ?? DEFAULT_META;

    return (
        <div className="min-h-screen flex flex-col">
            <div className="flex-grow max-w-[1440px] mx-auto px-6 py-10 animate-fade-in relative z-10 w-full">
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">

                    {/* Left Side: Header + FAQ */}
                    <div className="lg:col-span-7 space-y-8">

                        {/* Page Header */}
                        <div className="text-left">
                            <div className="flex items-center gap-4 mb-3">
                                <MdOutlineFeedback size={38} className="text-blue-600 drop-shadow-sm" />
                                <h1 className="text-4xl font-extrabold text-slate-800 tracking-tight">意見回饋中心</h1>
                            </div>
                            <p className="text-slate-500 font-medium leading-relaxed max-w-2xl">
                                您的建議是我們進步的動力！<br />如果您在使用過程中遇到任何問題，或有任何建議，歡迎隨時讓我們知道。
                            </p>
                        </div>

                        {/* FAQ Section */}
                        <div className="space-y-5">

                            {/* FAQ Section Header */}
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 bg-blue-50 rounded-lg">
                                        <svg className="text-blue-500 w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                                        </svg>
                                    </div>
                                    <h2 className="text-2xl font-bold text-slate-800">常見問題 (FAQ)</h2>
                                    <span className="text-sm font-semibold text-slate-400 bg-slate-100 px-2.5 py-0.5 rounded-full">
                                        {filteredFaqs.length} 則
                                    </span>
                                </div>
                            </div>

                            {/* Search Bar */}
                            <div className="relative">
                                <FaSearch className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-sm" />
                                <input
                                    ref={searchInputRef}
                                    type="text"
                                    value={searchQuery}
                                    onChange={e => setSearchQuery(e.target.value)}
                                    placeholder="搜尋問題或關鍵字..."
                                    className="w-full pl-10 pr-10 py-3 rounded-xl border border-gray-200 bg-white text-sm text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-200 focus:border-blue-400 transition-all duration-200 shadow-sm"
                                />
                                {searchQuery && (
                                    <button
                                        onClick={handleClearSearch}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors p-1"
                                    >
                                        <FaTimes size={13} />
                                    </button>
                                )}
                            </div>

                            {/* Category Dropdown */}
                            <div className="relative" ref={dropdownRef}>
                                <button
                                    type="button"
                                    onClick={() => setCategoryDropdownOpen(prev => !prev)}
                                    className="
                                        w-full flex items-center justify-between gap-3
                                        px-4 py-3 rounded-xl border border-gray-200 bg-white
                                        text-sm font-semibold text-slate-700
                                        hover:border-blue-300 hover:bg-blue-50/30
                                        focus:outline-none focus:ring-2 focus:ring-blue-200
                                        transition-all duration-200 shadow-sm
                                    "
                                >
                                    <div className="flex items-center gap-2.5">
                                        <span className={`flex items-center justify-center w-6 h-6 rounded-lg text-xs font-bold ${selectedCategory === ALL_CATEGORY
                                                ? 'bg-slate-100 text-slate-500'
                                                : `${selectedMeta.bg} ${selectedMeta.color}`
                                            }`}>
                                            {selectedCategory === ALL_CATEGORY ? '全' : selectedMeta.icon}
                                        </span>
                                        <span>{selectedCategory}</span>
                                        <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${selectedCategory === ALL_CATEGORY
                                                ? 'bg-slate-100 text-slate-500'
                                                : `${selectedMeta.bg} ${selectedMeta.color}`
                                            }`}>
                                            {filteredFaqs.length} 則
                                        </span>
                                    </div>
                                    <FaChevronDown
                                        size={13}
                                        className={`text-slate-400 transition-transform duration-200 ${categoryDropdownOpen ? 'rotate-180' : ''
                                            }`}
                                    />
                                </button>

                                {/* Dropdown Panel */}
                                {categoryDropdownOpen && (
                                    <div className="
                                        absolute z-20 top-[calc(100%+6px)] left-0 right-0
                                        bg-white border border-gray-200 rounded-2xl shadow-xl
                                        overflow-hidden animate-fade-in
                                    ">
                                        <div className="p-1.5 max-h-72 overflow-y-auto custom-scrollbar">
                                            {faqCategories.map(cat => {
                                                const meta = CATEGORY_META[cat] ?? DEFAULT_META;
                                                const isActive = selectedCategory === cat;
                                                const count = countForCategory(cat);
                                                if (count === 0 && cat !== ALL_CATEGORY) return null;
                                                return (
                                                    <button
                                                        key={cat}
                                                        type="button"
                                                        onClick={() => {
                                                            handleCategorySelect(cat);
                                                            setCategoryDropdownOpen(false);
                                                        }}
                                                        className={`
                                                            w-full flex items-center gap-3 px-3 py-2.5 rounded-xl
                                                            text-sm font-semibold text-left transition-all duration-150
                                                            ${isActive
                                                                ? `${meta.activeBg} ${meta.activeText}`
                                                                : 'text-slate-700 hover:bg-slate-50'
                                                            }
                                                        `}
                                                    >
                                                        <span className={`
                                                            flex items-center justify-center w-6 h-6 rounded-lg text-xs font-bold flex-shrink-0
                                                            ${isActive
                                                                ? 'bg-white/25 text-white'
                                                                : `${meta.bg} ${meta.color}`
                                                            }
                                                        `}>
                                                            {cat === ALL_CATEGORY ? '全' : meta.icon}
                                                        </span>
                                                        <span className="flex-1">{cat}</span>
                                                        <span className={`
                                                            text-xs px-2 py-0.5 rounded-full font-bold
                                                            ${isActive
                                                                ? 'bg-white/25 text-white'
                                                                : `${meta.bg} ${meta.color}`
                                                            }
                                                        `}>
                                                            {count}
                                                        </span>
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* FAQ Items */}
                            <div className="space-y-2.5">
                                {filteredFaqs.length > 0 ? (
                                    filteredFaqs.map((item, idx) => {
                                        const isOpen = openFaqIds.has(item.id);
                                        const itemMeta = CATEGORY_META[item.category] ?? DEFAULT_META;
                                        return (
                                            <div
                                                key={item.id}
                                                className={`
                                                    bg-white rounded-2xl border transition-all duration-300 overflow-hidden
                                                    ${isOpen
                                                        ? `border-blue-200 shadow-[0_4px_20px_-4px_rgba(59,130,246,0.15)]`
                                                        : 'border-gray-100 shadow-sm hover:shadow-md hover:border-gray-200'
                                                    }
                                                `}
                                                style={{ animationDelay: `${idx * 30}ms` }}
                                            >
                                                <button
                                                    onClick={() => handleToggleFaq(item.id)}
                                                    className="w-full flex items-center gap-4 p-4 text-left"
                                                >
                                                    {/* Q Badge */}
                                                    <div className={`
                                                        w-9 h-9 rounded-xl flex items-center justify-center font-bold text-base flex-shrink-0
                                                        transition-colors duration-200
                                                        ${isOpen ? 'bg-blue-600 text-white' : `${itemMeta.bg} ${itemMeta.color}`}
                                                    `}>
                                                        Q
                                                    </div>

                                                    <span className={`
                                                        flex-1 font-semibold text-[15px] leading-snug transition-colors duration-200
                                                        ${isOpen ? 'text-blue-700' : 'text-slate-800'}
                                                    `}>
                                                        {item.question}
                                                    </span>

                                                    {/* Category tag - only shown in 全部 view */}
                                                    {selectedCategory === ALL_CATEGORY && (
                                                        <span className={`
                                                            hidden sm:flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-lg
                                                            flex-shrink-0 ${itemMeta.bg} ${itemMeta.color}
                                                        `}>
                                                            {itemMeta.icon}
                                                            {item.category}
                                                        </span>
                                                    )}

                                                    <span className={`
                                                        ml-2 flex-shrink-0 transition-transform duration-300
                                                        ${isOpen ? 'rotate-180 text-blue-500' : 'text-gray-400'}
                                                    `}>
                                                        <FaChevronDown size={15} />
                                                    </span>
                                                </button>

                                                {/* Answer Panel */}
                                                <div className={`
                                                    overflow-hidden transition-all duration-300
                                                    ${isOpen ? 'max-h-[600px] opacity-100' : 'max-h-0 opacity-0'}
                                                `}>
                                                    <div className="px-5 pb-5 pt-1 ml-[52px]">
                                                        <div className="h-px bg-gradient-to-r from-blue-100 to-transparent mb-4" />
                                                        <p className="text-slate-600 leading-relaxed text-[15px]">
                                                            {item.answer}
                                                        </p>
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })
                                ) : (
                                    <div className="py-16 text-center bg-white rounded-2xl border border-dashed border-gray-200">
                                        <FaSearch className="mx-auto text-3xl text-slate-300 mb-3" />
                                        <p className="text-slate-400 font-semibold">
                                            {searchQuery ? `找不到包含「${searchQuery}」的問題` : '此分類尚無問題'}
                                        </p>
                                        {searchQuery && (
                                            <button
                                                onClick={handleClearSearch}
                                                className="mt-2 text-sm text-blue-500 hover:text-blue-700 font-medium"
                                            >
                                                清除搜尋
                                            </button>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Right Side: Feedback Form */}
                    <div className="lg:col-span-5 h-fit lg:sticky lg:top-5">
                        <div className="bg-white rounded-[40px] border border-gray-100 shadow-[0_32px_64px_-16px_rgba(0,30,100,0.12)] overflow-hidden flex flex-col max-h-[calc(100vh-125px)] relative">

                            {/* Header */}
                            <div className="bg-gradient-to-r from-blue-700 to-blue-500 px-8 py-6 flex items-center gap-6 relative overflow-hidden">
                                <div className="absolute -top-10 -right-10 w-40 h-40 bg-white/10 blur-3xl rounded-full" />
                                <div className="absolute -bottom-5 -left-5 w-24 h-24 bg-blue-400/20 blur-2xl rounded-full" />
                                <FaPaperPlane className="text-white text-3xl flex-shrink-0" />
                                <div className="relative z-10">
                                    <h2 className="text-2xl font-bold text-white tracking-tight">問題回報與建議</h2>
                                    <p className="text-blue-50/90 text-[13px] font-medium mt-1 uppercase tracking-wider">我們會認真閱讀每一份回饋</p>
                                </div>
                            </div>

                            {/* Scrollable Form */}
                            <div className="flex-1 overflow-y-auto p-8 custom-scrollbar bg-slate-50/20">
                                <form onSubmit={handleSubmit} className="space-y-8">

                                    {/* Categorized Problem Types */}
                                    <div>
                                        <label className="block text-base font-bold text-slate-800 mb-5 flex items-center gap-2">
                                            <span className="w-2 h-5 bg-blue-600 rounded-full"></span>
                                            您可能遇到的問題 (可複選)
                                        </label>

                                        <div className="space-y-4">
                                            {Object.entries(groupedProblemTypes)
                                                .filter(([category]) => category !== '其他')
                                                .map(([category, items]) => (
                                                    <div key={category} className="border border-gray-200 rounded-2xl overflow-hidden bg-gray-50/40 shadow-sm">
                                                        <button
                                                            type="button"
                                                            onClick={() => toggleProblemCategory(category)}
                                                            className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-white transition-colors border-b border-transparent group"
                                                        >
                                                            <span className="text-[15px] font-bold text-slate-700 group-hover:text-blue-600">{category}</span>
                                                            {openProblemCategories.includes(category) ? <FaChevronUp size={14} className="text-blue-500" /> : <FaChevronDown size={14} className="text-gray-400" />}
                                                        </button>

                                                        {openProblemCategories.includes(category) && (
                                                            <div className="px-4 pb-4 pt-1 grid grid-cols-1 gap-2 animate-slide-down bg-white/60">
                                                                {items.map((type) => (
                                                                    <button
                                                                        key={type.id}
                                                                        type="button"
                                                                        onClick={() => handleToggleProblem(type.id)}
                                                                        className={`
                                                                            flex items-center gap-3 p-3 rounded-xl border text-left transition-all duration-200
                                                                            ${selectedProblems.includes(type.id)
                                                                                ? 'bg-blue-50 border-blue-300 text-blue-700 shadow-sm'
                                                                                : 'bg-white border-transparent hover:border-gray-100 text-slate-600'
                                                                            }
                                                                        `}
                                                                    >
                                                                        <div className={`
                                                                            w-5 h-5 rounded-md border flex items-center justify-center transition-colors
                                                                            ${selectedProblems.includes(type.id)
                                                                                ? 'bg-blue-600 border-blue-600 shadow-sm'
                                                                                : 'bg-white border-gray-300'
                                                                            }
                                                                        `}>
                                                                            {selectedProblems.includes(type.id) && (
                                                                                <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}>
                                                                                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                                                                </svg>
                                                                            )}
                                                                        </div>
                                                                        <span className="text-[14px] font-semibold">{type.label}</span>
                                                                    </button>
                                                                ))}
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}

                                            {/* Other category */}
                                            {problemTypes.filter(p => p.category === '其他').map(type => (
                                                <div key={type.id} className="border border-gray-200 rounded-2xl overflow-hidden bg-gray-50/40 shadow-sm">
                                                    <button
                                                        type="button"
                                                        onClick={() => handleToggleProblem(type.id)}
                                                        className={`
                                                            w-full flex items-center gap-4 p-5 text-left transition-all duration-200
                                                            ${selectedProblems.includes(type.id)
                                                                ? 'bg-blue-50 text-blue-700 font-bold'
                                                                : 'bg-transparent text-slate-600 hover:bg-white'
                                                            }
                                                        `}
                                                    >
                                                        <div className={`
                                                            w-6 h-6 rounded-md border flex items-center justify-center transition-colors flex-shrink-0
                                                            ${selectedProblems.includes(type.id)
                                                                ? 'bg-blue-600 border-blue-600 shadow-sm'
                                                                : 'bg-white border-gray-300'
                                                            }
                                                        `}>
                                                            {selectedProblems.includes(type.id) && (
                                                                <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={4}>
                                                                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                                                </svg>
                                                            )}
                                                        </div>
                                                        <span className="text-[15px] font-bold">{type.label}</span>
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Description */}
                                    <div>
                                        <label className="block text-base font-bold text-slate-800 mb-5 flex items-center gap-2">
                                            <span className="w-2 h-5 bg-blue-600 rounded-full"></span>
                                            詳細描述您遇到的問題
                                        </label>
                                        <textarea
                                            value={description}
                                            onChange={(e) => setDescription(e.target.value)}
                                            placeholder="請填寫具體情況，這能幫助我們更快解決問題..."
                                            rows={4}
                                            className="
                                                w-full p-5 rounded-2xl border border-gray-200 bg-gray-50/50
                                                focus:bg-white focus:ring-4 focus:ring-blue-100 focus:border-blue-500
                                                transition-all duration-200 outline-none resize-none text-[15px] text-slate-700
                                            "
                                        />
                                    </div>

                                    <div className="flex justify-end pt-2">
                                        <button
                                            type="submit"
                                            disabled={submitting}
                                            className={`
                                                px-10 py-3.5 rounded-xl font-bold text-white text-base
                                                transition-all duration-300 flex items-center justify-center gap-3
                                                ${submitting
                                                    ? 'bg-blue-400 cursor-not-allowed'
                                                    : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-lg shadow-blue-600/20 hover:shadow-indigo-600/30 hover:-translate-y-0.5 active:scale-[0.98]'
                                                }
                                            `}
                                        >
                                            {submitting ? (
                                                <>
                                                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                                    <span>提交中...</span>
                                                </>
                                            ) : (
                                                <>
                                                    <FaPaperPlane className="text-lg" />
                                                    <span>提交回饋</span>
                                                </>
                                            )}
                                        </button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <Footer />

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

export default FeedbackCenter;
