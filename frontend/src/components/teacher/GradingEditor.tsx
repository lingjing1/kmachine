import { useState, useEffect } from 'react';
import { FaRedo, FaQuestionCircle, FaRobot, FaSpinner } from 'react-icons/fa';
import ReactMarkdown from 'react-markdown';

import {
    parseQuestionsFromContent,
    distributePoints,
    GradingConfig,
    QuestionTypeGrading,
    QUESTION_TYPE_NAMES,
    ValidationResult
} from '../../utils/grading';



interface GradingEditorProps {
    content: any; // The generated content structure
    config: GradingConfig;
    onChange: (config: GradingConfig) => void;
    onContentUpdate?: (newContent: any) => void;
    onValidate?: (result: ValidationResult) => void;
    onQuestionClick?: (questionIndex: number) => void;
    showCriticPrompt?: boolean; // Whether to show AI suggestion prompt
    onRequestCritic?: () => void; // Trigger Critic evaluation
    isCriticLoading?: boolean; // Loading state for critic
    className?: string;
    version?: number;
}

export function GradingEditor({
    content,
    config,
    onChange,
    onContentUpdate,
    onValidate,
    onQuestionClick,
    showCriticPrompt = false,
    onRequestCritic,
    isCriticLoading = false,
    className = '',
    version = 0
}: GradingEditorProps) {
    const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
    const [showTip, setShowTip] = useState(false);

    // Initial parsing
    // Initial parsing & Sync on content change
    useEffect(() => {
        if (content) {
            const parsed = parseQuestionsFromContent(content);
            const totalQuestions = parsed.questions.length;

            if (parsed.types.length > 0) {
                // Determine if we are syncing with existing config or initializing
                const isInitializing = config.question_types.length === 0;

                // Smart Distribution Logic parameters
                const targetTotal = config.total_points || 100;
                const basePoints = totalQuestions > 0 ? Math.floor(targetTotal / totalQuestions) : 0;
                const remainder = totalQuestions > 0 ? targetTotal % totalQuestions : 0;

                // 1. Setup Types (Base points only)
                const newTypes = parsed.types.map(t => ({
                    ...t,
                    points_per_question: basePoints,
                    total_points: t.question_count * basePoints
                }));

                // 2. Setup Individuals with Preservation
                const oldQuestions = config.individual_questions || [];

                const newIndiv = parsed.questions.map((q, idx) => {
                    // Try to preserve points from existing config
                    // Match by text primarily, or fallback to exact path match if positions didn't change (less likely on reorder)
                    let preservedPoints = -1;

                    if (!isInitializing && oldQuestions.length > 0) {
                        const match = oldQuestions.find(oq =>
                            (q.text && oq.text === q.text && oq.question_type === q.question_type)
                        );
                        if (match) {
                            preservedPoints = match.points;
                        }
                    }

                    // If preservation found, use it. Otherwise calculate default.
                    if (preservedPoints >= 0) {
                        return { ...q, points: preservedPoints };
                    }

                    // Default calculation (Base + Remainder to LAST question)
                    const isLast = idx === totalQuestions - 1;
                    return {
                        ...q,
                        points: basePoints + (isLast ? remainder : 0)
                    };
                });

                // Recalculate type totals based on preserved/new individuals to keep things consistent if we are in 'by_question_type' mode
                // Actually if points are chaotic, we might force 'by_individual_question' or just update the types summary to reflect average?
                // For simplicity, we just update the config. 
                // Note: If using 'by_question_type', the individual points might be overwritten by type logic if user edits type settings. 
                // But here we are just syncing list.

                // 3. Decide Method
                // Keep existing method if initialized, otherwise decide
                // Default to by_question_type as per requirement
                const defaultMethod = isInitializing
                    ? 'by_question_type'
                    : config.grading_method;

                onChange({
                    ...config,
                    grading_method: defaultMethod,
                    question_types: newTypes,
                    individual_questions: newIndiv
                });
            }
        }
    }, [content, version]);

    // Validation
    const validate = (currentConfig: GradingConfig): ValidationResult => {
        const errors: string[] = [];
        let calculatedTotal = 0;

        if (currentConfig.grading_method === 'by_question_type') {
            calculatedTotal = currentConfig.question_types.reduce((sum, t) => sum + t.total_points, 0);
        } else {
            // Safe check if individual_questions is defined
            const questions = currentConfig.individual_questions || [];
            calculatedTotal = questions.reduce((sum, q) => sum + q.points, 0);
        }

        // Checking consistency
        if (Math.abs(calculatedTotal - currentConfig.total_points) > 0.1) {
            errors.push(`配分總和 (${Number(calculatedTotal.toFixed(1))}) 與考卷總分 (${currentConfig.total_points}) 不一致`);
        }

        return { isValid: errors.length === 0, errors };
    };

    // Run validation on config change
    useEffect(() => {
        const result = validate(config);
        setValidationResult(result);
        if (onValidate) onValidate(result);
    }, [config]);

    const handleTypeChange = (index: number, field: keyof QuestionTypeGrading, value: number) => {
        const newTypes = [...config.question_types];
        newTypes[index] = { ...newTypes[index], [field]: value };

        // Auto update total_points for that type
        if (field === 'points_per_question' || field === 'question_count') {
            // Force integer calculation
            newTypes[index].total_points = newTypes[index].question_count * newTypes[index].points_per_question;
        }

        onChange({ ...config, question_types: newTypes });
    };

    const handleIndividualChange = (index: number, field: 'points' | 'question_id', value: number | string) => {
        if (!config.individual_questions) return;
        const newQs = [...config.individual_questions];

        if (field === 'points') {
            newQs[index] = { ...newQs[index], points: Number(value) };
        } else if (field === 'question_id') {
            newQs[index] = { ...newQs[index], question_id: value };

            // Sync to content if possible
            if (onContentUpdate && (newQs[index] as any).path) {
                const path = (newQs[index] as any).path; // [blockIdx, qIdx]
                const [blockIdx, qIdx] = path;

                let newContentStructure = null;
                if (Array.isArray(content)) {
                    newContentStructure = [...content];
                    newContentStructure[blockIdx] = { ...newContentStructure[blockIdx], questions: [...newContentStructure[blockIdx].questions] };
                    newContentStructure[blockIdx].questions[qIdx] = { ...newContentStructure[blockIdx].questions[qIdx], question_number: value };
                } else if (content.type === 'exam_questions' && Array.isArray(content.content)) {
                    newContentStructure = { ...content, content: [...content.content] };
                    newContentStructure.content[blockIdx] = { ...newContentStructure.content[blockIdx], questions: [...newContentStructure.content[blockIdx].questions] };
                    newContentStructure.content[blockIdx].questions[qIdx] = { ...newContentStructure.content[blockIdx].questions[qIdx], question_number: value };
                } else if (Array.isArray(content.content)) {
                    // content.content wrapper
                    newContentStructure = { ...content, content: [...content.content] };
                    newContentStructure.content[blockIdx] = { ...newContentStructure.content[blockIdx], questions: [...newContentStructure.content[blockIdx].questions] };
                    newContentStructure.content[blockIdx].questions[qIdx] = { ...newContentStructure.content[blockIdx].questions[qIdx], question_number: value };
                }

                if (newContentStructure) {
                    onContentUpdate(newContentStructure);
                }
            }
        }
        onChange({ ...config, individual_questions: newQs });
    };

    const calculateCurrentTotal = () => {
        if (config.grading_method === 'by_question_type') {
            return config.question_types.reduce((sum, t) => sum + t.total_points, 0);
        } else {
            return (config.individual_questions || []).reduce((sum, q) => sum + q.points, 0);
        }
    };

    const currentTotal = calculateCurrentTotal();

    const handleAutoFix = () => {
        const currentScore = calculateCurrentTotal();
        const diff = config.total_points - currentScore;
        if (diff === 0) return;

        let newIndividuals = [...(config.individual_questions || [])];

        // If currently in 'by_question_type', we need to sync values first from the current type settings
        // because individual_questions might be stale
        if (config.grading_method === 'by_question_type') {
            const typePointsMap = new Map(config.question_types.map(t => [t.type_id, t.points_per_question]));
            newIndividuals = newIndividuals.map(q => ({
                ...q,
                points: typePointsMap.get(q.question_type) || 0
            }));
        }

        // Apply diff to the last item
        if (newIndividuals.length > 0) {
            const lastIdx = newIndividuals.length - 1;
            // Ensure we don't go negative if diff is negative (user over-allocated)
            // But usually user wants to fill up. If over-allocated, we subtract.
            // Check if result is valid? >= 0.
            const newPoint = newIndividuals[lastIdx].points + diff;
            if (newPoint >= 0) {
                newIndividuals[lastIdx] = {
                    ...newIndividuals[lastIdx],
                    points: newPoint
                };
            }
        }

        onChange({
            ...config,
            grading_method: 'by_individual_question',
            individual_questions: newIndividuals
        });
    };

    const handleReset = () => {
        const parsed = parseQuestionsFromContent(content);
        if (parsed.questions.length > 0) {
            const totalPoints = config.total_points || 100;
            const { questions, types } = distributePoints(parsed.questions, totalPoints);
            // const hasRemainder = totalPoints % parsed.questions.length !== 0;

            // User requested to STAY in the current mode regardless of remainder
            // So we simply use the current config.grading_method

            onChange({
                ...config,
                grading_method: config.grading_method,
                question_types: types,
                individual_questions: questions
            });
        }
    };

    return (
        <div className={`flex flex-col h-full ${className}`}>
            <div className="flex-1 w-full max-w-[85%] mx-auto py-6 flex flex-col min-h-0">

                {/* 1. Grading Method Switcher - Segmented Control */}
                <div className="flex justify-center mb-6 shrink-0">
                    <div className="bg-gray-100 p-1 rounded-full flex relative w-full shadow-inner max-w-sm">
                        <button
                            className={`flex-1 py-1.5 px-3 rounded-full text-sm font-bold transition-all duration-200 ${config.grading_method === 'by_question_type'
                                ? 'bg-white text-blue-700 shadow-sm ring-1 ring-black/5'
                                : 'text-gray-500 hover:text-gray-700'
                                }`}
                            onClick={() => onChange({ ...config, grading_method: 'by_question_type' })}
                        >
                            依題型配分
                        </button>
                        <button
                            className={`flex-1 py-1.5 px-3 rounded-full text-sm font-bold transition-all duration-200 ${config.grading_method === 'by_individual_question'
                                ? 'bg-white text-blue-700 shadow-sm ring-1 ring-black/5'
                                : 'text-gray-500 hover:text-gray-700'
                                }`}
                            onClick={() => onChange({ ...config, grading_method: 'by_individual_question' })}
                        >
                            每題配分
                        </button>
                    </div>
                </div>

                {/* 2. Controls Bar: Score (Left) | Actions (Right) */}
                <div className="flex justify-between items-end mb-4 shrink-0 border-b border-gray-100 pb-4">
                    {/* Left: Total Score Dashboard */}
                    <div className="flex flex-col gap-2 flex-1">
                        <div className="flex items-center gap-2">
                            <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">滿分設定</label>
                            {/* Help Tooltip - Moved next to label */}
                            <div className="relative">
                                <button
                                    onClick={() => setShowTip(!showTip)}
                                    className="text-gray-400 hover:text-blue-600 transition-colors"
                                    title="說明"
                                >
                                    <FaQuestionCircle size={14} />
                                </button>
                                {showTip && (
                                    <>
                                        <div className="fixed inset-0 z-40 cursor-default" onClick={() => setShowTip(false)}></div>
                                        <div className="absolute left-0 top-6 z-50 w-64 p-4 bg-gray-800 text-white text-xs rounded-xl shadow-2xl leading-relaxed cursor-auto">
                                            <p className="font-bold mb-1 text-gray-200">配分說明</p>
                                            配分設定將會影響自動評分與成績計算。儲存後仍可在「作業/考試管理」中修改。
                                            <div className="absolute -top-1 left-1.5 w-3 h-3 bg-gray-800 rotate-45"></div>
                                        </div>
                                    </>
                                )}
                            </div>
                        </div>
                        <div className="flex items-center gap-4">
                            {/* Target Score Input */}
                            <div className="relative group w-24">
                                <input
                                    type="number"
                                    value={config.total_points}
                                    onChange={(e) => onChange({ ...config, total_points: parseFloat(e.target.value) || 0 })}
                                    className="w-full pl-3 pr-8 py-1.5 border border-gray-200 rounded-lg text-lg font-bold text-gray-800 focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-50 transition-all text-left"
                                />
                                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-bold text-gray-400">分</span>
                            </div>

                            {/* Dashboard Status Ring */}
                            <div className={`flex items-center gap-3 px-4 py-2 rounded-xl border transition-all ${currentTotal === config.total_points
                                ? 'bg-green-50 border-green-200 text-green-700'
                                : currentTotal > config.total_points
                                    ? 'bg-red-50 border-red-200 text-red-700'
                                    : 'bg-gray-100 border-gray-200 text-gray-600'
                                }`}>
                                <div className="text-xs font-bold opacity-70">目前配分</div>
                                <div className="text-2xl font-black tracking-tight leading-none">
                                    {Number(currentTotal.toFixed(1))}
                                </div>
                                {currentTotal === config.total_points ? (
                                    <div className="w-6 h-6 rounded-full bg-green-500 text-white flex items-center justify-center shadow-sm">
                                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                        </svg>
                                    </div>
                                ) : (
                                    <span className="text-sm font-bold opacity-70">分</span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Right: Actions */}
                    <div className="flex items-center gap-2">
                        <button
                            onClick={handleReset}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-gray-500 hover:text-blue-600 hover:bg-blue-50 transition-all border border-transparent hover:border-blue-100"
                            title="重新自動平均分配"
                        >
                            <FaRedo className={isCriticLoading ? "animate-spin" : ""} />
                            重置
                        </button>
                    </div>
                </div>

                {/* Editor Area */}
                {
                    config.grading_method === 'by_question_type' ? (
                        <div className="space-y-4 flex-1 overflow-y-auto min-h-0 pr-1 scrollbar-thin">
                            {config.question_types.map((type, idx) => (
                                <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200 text-sm hover:bg-white hover:shadow-sm transition-all">
                                    {/* Left: Name and Count */}
                                    <div className="flex items-center gap-3">
                                        <span className="font-bold text-gray-700">{type.type_name}</span>
                                        <span className="text-xs text-gray-500 bg-white px-2 py-0.5 rounded border border-gray-200">
                                            {type.question_count}題
                                        </span>
                                    </div>

                                    {/* Right: Inputs and Totals */}
                                    <div className="flex items-center gap-4">
                                        {/* Points per question */}
                                        <div className="flex items-center gap-1.5">
                                            <input
                                                type="number"
                                                min="0"
                                                value={type.points_per_question}
                                                onChange={(e) => handleTypeChange(idx, 'points_per_question', parseInt(e.target.value) || 0)}
                                                className="w-14 px-1.5 py-1 border border-gray-300 rounded text-center font-bold text-gray-700 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-200 bg-white"
                                            />
                                            <span className="text-xs text-gray-500">分 / 題</span>
                                        </div>

                                        {/* Total Points */}
                                        <div className="flex items-center gap-1 w-20 justify-end">
                                            <span className="text-xs text-gray-400">共</span>
                                            <span className="font-bold text-gray-800 text-base">
                                                {type.total_points}
                                            </span>
                                            <span className="text-xs text-gray-400">分</span>
                                        </div>
                                    </div>
                                </div>
                            ))}
                            {config.question_types.length === 0 && (
                                <p className="text-gray-500 text-center py-4 text-sm">未偵測到題目類型</p>
                            )}
                        </div>
                    ) : (
                        <div className="space-y-2 flex-1 overflow-y-auto min-h-0 pr-1 scrollbar-thin scrollbar-thumb-gray-200">
                            {config.individual_questions && config.individual_questions.map((q, idx) => (
                                <div
                                    key={idx}
                                    onClick={() => onQuestionClick && onQuestionClick(Number(q.question_id))}
                                    className="flex items-center gap-3 p-2 bg-gray-50 rounded border border-gray-100 text-sm hover:bg-white hover:shadow-sm transition-all cursor-pointer group"
                                >
                                    <div className="flex flex-col items-center justify-center w-10 shrink-0 gap-1 self-start pt-0.5">
                                        <div className="text-blue-600 font-mono text-xs font-bold">
                                            {String(q.question_id).padStart(2, '0')}
                                        </div>
                                        <span className="text-[10px] text-gray-400 font-medium bg-white px-1 rounded border border-gray-100 whitespace-nowrap overflow-hidden text-ellipsis max-w-full">
                                            {QUESTION_TYPE_NAMES[q.question_type] || q.question_type}
                                        </span>
                                    </div>

                                    <div className="flex flex-col flex-1 min-w-0 self-center">
                                        {q.text ? (
                                            <div className="text-gray-700 line-clamp-2 text-xs font-bold leading-relaxed overflow-hidden">
                                                <ReactMarkdown>
                                                    {q.text}
                                                </ReactMarkdown>
                                            </div>
                                        ) : (
                                            <span className="text-gray-400 italic text-xs">無題目內容</span>
                                        )}


                                    </div>

                                    <div className="flex items-center gap-1 shrink-0 self-center">
                                        <input
                                            type="number"
                                            min="0"
                                            value={q.points}
                                            onChange={(e) => handleIndividualChange(idx, 'points', parseInt(e.target.value) || 0)}
                                            className="w-16 px-2 py-1.5 border rounded text-right font-bold text-gray-700 bg-white focus:outline-none focus:border-theme-primary text-sm"
                                        />
                                        <span className="text-gray-400 text-xs translate-y-0.5">分</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                {
                    !validationResult?.isValid && validationResult?.errors && (
                        <div className="mt-2 shrink-0">
                            <div className="flex items-center justify-between px-3 py-2 rounded bg-red-50 border border-red-100">
                                <span className="text-xs text-red-600 font-bold flex-1 truncate mr-2" title={validationResult.errors[0]}>
                                    {validationResult.errors[0]}
                                </span>
                                <button
                                    onClick={handleAutoFix}
                                    className="text-xs bg-white border border-red-200 text-red-600 hover:bg-red-600 hover:text-white px-2 py-0.5 rounded transition-colors font-bold shadow-sm whitespace-nowrap"
                                >
                                    自動補齊
                                </button>
                            </div>
                        </div>
                    )
                }

                {/* AI Critic Prompt Section */}
                {
                    showCriticPrompt && onRequestCritic && (
                        <div className="mt-4 pt-4 border-t border-gray-200 shrink-0">
                            <div className="p-4 bg-gradient-to-r from-blue-50 to-blue-100 rounded-lg border border-blue-200">
                                <div className="flex items-center gap-2 mb-2">
                                    <FaRobot className="text-blue-600" />
                                    <h4 className="font-bold text-blue-900">🤖 AI 批改建議</h4>
                                </div>
                                <p className="text-sm text-blue-700 mb-3">
                                    生成 AI 批改與優化建議，幫助改進題目品質
                                </p>
                                <button
                                    onClick={onRequestCritic}
                                    disabled={isCriticLoading}
                                    className="w-full py-2 px-4 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-bold rounded-lg hover:from-blue-600 hover:to-blue-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                                >
                                    {isCriticLoading ? (
                                        <>
                                            <FaSpinner className="animate-spin" />
                                            <span>分析中...</span>
                                        </>
                                    ) : (
                                        <span>開始分析</span>
                                    )}
                                </button>
                            </div>
                        </div>
                    )
                }
            </div >
        </div >
    );
}
