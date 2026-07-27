import { useState, useEffect } from 'react';
import { FaCheckCircle, FaExclamationTriangle, FaTimesCircle, FaSpinner, FaChevronDown, FaChevronUp, FaExpandAlt, FaHistory, FaSync } from 'react-icons/fa';
import { EvaluationResponse, fetchCriticEvaluations, fetchEvaluationHistory } from '../../services/criticApi';
import Modal from '../common/Modal';
import { formatDateTime } from '../../utils/dateUtils';

// Helper: Score Visualization
// Helper: Score Visualization
const ScoreBar = ({ score, max = 5, showText = true }: { score: number; max?: number; showText?: boolean }) => {
    const ratio = Math.min(score / max, 1);
    let colorClass = 'bg-green-500';
    if (ratio < 0.6) colorClass = 'bg-red-500';
    else if (ratio < 0.8) colorClass = 'bg-yellow-500';

    return (
        <div className="flex items-center gap-2">
            <div className="flex gap-1">
                {[...Array(max)].map((_, i) => (
                    <div
                        key={i}
                        className={`h-2 w-3 sm:w-4 rounded-sm transition-all ${i < Math.round(score) ? colorClass : 'bg-gray-200'
                            }`}
                    />
                ))}
            </div>
            {showText && <span className={`text-xs font-bold ml-1 ${ratio >= 0.8 ? 'text-green-600' : ratio >= 0.6 ? 'text-yellow-600' : 'text-red-500'}`}>{score}/{max}</span>}
        </div>
    );
};

// Helper to check content existence for rendering
const contentIsGeneratedQualityCritical = (qc: any) => {
    return qc && qc.evaluations && qc.evaluations.length > 0;
};



interface CriticResultPanelProps {
    jobId: number;
    evaluationData?: EvaluationResponse | null;
    onRefresh?: (workflow: 2 | 3 | 4) => Promise<void>;
    isLoading?: boolean;
    className?: string;
}

export default function CriticResultPanel({
    jobId,
    evaluationData: externalData,
    onRefresh,
    isLoading = false,
    className = ''
}: CriticResultPanelProps) {
    const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(externalData || null);
    const [history, setHistory] = useState<EvaluationResponse[]>([]);
    const [loading, setLoading] = useState(!externalData);
    const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['fact', 'quality']));
    const [selectedRubric, setSelectedRubric] = useState<any>(null); // For Modal


    // ... (rest of logic same) ...

    // Fetch evaluation data if not provided
    useEffect(() => {
        if (!externalData && jobId) {
            loadEvaluation();
        }
        else if (externalData) {
            setEvaluation(externalData);
            setLoading(false);
            // Also fetch history even if data provided ?? 
            // Maybe better to always fetch history if we have jobId
            if (jobId) loadHistory();
        }
    }, [jobId, externalData]);

    const loadEvaluation = async () => {
        setLoading(true);
        try {
            const data = await fetchCriticEvaluations(jobId);
            setEvaluation(data);
            await loadHistory();
        } catch (error) {
            console.error('Failed to load evaluation:', error);
        } finally {
            setLoading(false);
        }
    };

    const loadHistory = async () => {
        if (!jobId) return;
        try {
            const hist = await fetchEvaluationHistory(jobId);
            // Filter out current? Or show all
            setHistory(hist);
        } catch (e) {
            console.error("Failed to load history", e);
        }
    }

    const toggleSection = (section: string) => {
        const newExpanded = new Set(expandedSections);
        if (newExpanded.has(section)) {
            newExpanded.delete(section);
        } else {
            newExpanded.add(section);
        }
        setExpandedSections(newExpanded);
    };

    const handleRefresh = () => {
        if (onRefresh) {
            onRefresh(4); // Default to full evaluation
        } else {
            loadEvaluation();
        }
    };


    if (loading || isLoading) {
        return (
            <div className={`bg-white rounded-xl border border-gray-200 p-6 shadow-sm flex items-center justify-center ${className}`}>
                <div className="text-center">
                    <FaSpinner className="animate-spin text-theme-primary mx-auto mb-2" size={32} />
                    <p className="text-sm text-gray-600">Critic Agent 評估中...</p>
                </div>
            </div>
        );
    }

    if (!evaluation) {
        return (
            <div className={`bg-white rounded-xl border border-gray-200 p-6 shadow-sm ${className}`}>
                <div className="text-center text-gray-500">
                    <p className="mb-4">尚無評估結果</p>
                    <button
                        onClick={handleRefresh}
                        className="text-theme-primary hover:underline text-sm font-bold"
                    >
                        重新評估
                    </button>
                </div>
            </div>
        );
    }

    const { evaluation: evalData } = evaluation;

    return (
        <>
            <div className={`bg-white flex flex-col h-full ${className}`}>
                {/* Header - Simplified Status Bar */}
                {/* Header - Simplified Status Bar (Duration removed as per request) */}
                <div className="px-4 py-3 shrink-0 flex items-center justify-between bg-white hidden">
                    {/* Duration moved to history list */}
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto min-h-0 p-4 space-y-6">

                    {/* Evaluation Controls */}
                    <div className="space-y-2">
                        {/* Re-evaluation Button */}
                        <button
                            onClick={handleRefresh}
                            disabled={isLoading}
                            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-green-600 text-white rounded-xl hover:bg-green-700 transition-all font-bold text-sm shadow-md hover:shadow-lg disabled:opacity-50 group"
                        >
                            <FaSync size={14} className={`${isLoading ? 'animate-spin' : 'group-hover:rotate-180 transition-transform duration-500'}`} />
                            重新評估 AI 品質
                        </button>

                        {/* History Section */}
                        {history.length > 0 && (
                            <div className="space-y-2">
                                <button
                                    onClick={() => toggleSection('history')}
                                    className="w-full px-5 py-2.5 bg-green-50 hover:bg-green-100 transition-all flex items-center justify-center rounded-xl border border-green-100 shadow-sm group relative"
                                >
                                    <div className="flex items-center gap-2">
                                        <FaHistory className="text-green-600 group-hover:rotate-[-30deg] transition-transform" />
                                        <span className="font-bold text-green-800 text-sm">評估歷史紀錄</span>
                                    </div>
                                    <div className="absolute right-4">
                                        {expandedSections.has('history') ? <FaChevronUp className="text-green-500" size={12} /> : <FaChevronDown className="text-green-500" size={12} />}
                                    </div>
                                </button>

                                {expandedSections.has('history') && (
                                    <div className="divide-y divide-gray-100 bg-white max-h-48 overflow-y-auto border border-gray-100 rounded-xl shadow-inner ml-1 mr-1">
                                        {history.map((hist, index) => (
                                            <div
                                                key={index}
                                                className={`p-3 hover:bg-gray-40 cursor-pointer flex justify-between items-center transition-colors ${hist.evaluated_at === evaluation.evaluated_at ? 'bg-gray-50 shadow-inner' : ''}`}
                                                onClick={() => setEvaluation(hist)}
                                            >
                                                <div className="flex flex-col flex-1 min-w-0">
                                                    <div className="flex items-center">
                                                        <span className="text-xs font-bold text-gray-700 flex items-center gap-2">
                                                            {hist.evaluation.overall_passed ?
                                                                <span className="text-green-600 flex items-center gap-1"><FaCheckCircle size={10} /> 通過</span> :
                                                                <span className="text-red-500 flex items-center gap-1"><FaTimesCircle size={10} /> 未通過</span>
                                                            }
                                                            {index === 0 && <span className="bg-yellow-100 text-yellow-600 px-1.5 rounded text-[10px]">最新</span>}
                                                        </span>
                                                    </div>

                                                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                                                        <span className="text-xs text-gray-400">
                                                            {formatDateTime(hist.evaluated_at)}
                                                        </span>
                                                        {hist.duration_ms > 0 && (
                                                            <span className="text-[10px] text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                                                                {(hist.duration_ms / 1000).toFixed(1)}s
                                                            </span>
                                                        )}
                                                        {hist.workflow_name && (
                                                            <span className="text-[10px] text-gray-400 border border-gray-200 px-1 rounded">
                                                                {(() => {
                                                                    const map: Record<string, string> = {
                                                                        'fact_then_quality_quick': '完整評估',
                                                                        'fact_only_quick': '事實檢查',
                                                                        'quality_only_quick': '教學品質檢查'
                                                                    };
                                                                    return map[hist.workflow_name] || hist.workflow_name;
                                                                })()}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                                {hist.evaluated_at === evaluation.evaluated_at && (
                                                    <div className="ml-2 shrink-0">
                                                        <FaCheckCircle className="text-green-600" size={16} />
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Fact Critic Section */}
                    {evalData.fact_critic && (
                        <div>
                            <div className="flex items-center gap-3 mb-3 pb-2 border-b border-gray-100">
                                {evalData.fact_critic.passed ? (
                                    <FaCheckCircle className="text-green-500" />
                                ) : (
                                    <FaTimesCircle className="text-red-500" />
                                )}
                                <span className="font-bold text-gray-800">事實檢查 (Fact Check)</span>
                            </div>

                            <div className="space-y-4">
                                {/* Faithfulness */}
                                <div className="bg-white border border-gray-100 rounded-lg p-3 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
                                    onClick={() => setSelectedRubric({
                                        rubric_name: '事實準確性 (Faithfulness)',
                                        rating: evalData.fact_critic!.faithfulness.score,
                                        analysis: evalData.fact_critic!.faithfulness.analysis,
                                        suggestions: evalData.fact_critic!.faithfulness.suggestions
                                    })}
                                >
                                    <div className="flex justify-between items-center mb-2">
                                        <span className="text-sm font-bold text-gray-800 flex items-center gap-2">
                                            事實準確性
                                            <FaExpandAlt className="text-gray-400 text-xs" />
                                        </span>
                                        <ScoreBar score={evalData.fact_critic.faithfulness.score} />
                                    </div>
                                    <p className="text-xs text-gray-500 line-clamp-2">
                                        {evalData.fact_critic.faithfulness.analysis}
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Quality Critic Section */}
                    {evalData.quality_critic && (contentIsGeneratedQualityCritical(evalData.quality_critic)) && (
                        <div>
                            <div className="flex items-center gap-3 mb-3 pb-2 border-b border-gray-100">
                                {evalData.quality_critic.passed ? (
                                    <FaCheckCircle className="text-green-500" />
                                ) : (
                                    <FaExclamationTriangle className="text-yellow-500" />
                                )}
                                <span className="font-bold text-gray-800">教學品質 (Quality Check)</span>
                            </div>

                            <div className="space-y-3">
                                {evalData.quality_critic.evaluations.map((rubric, idx) => (
                                    <div
                                        key={idx}
                                        className="bg-white border border-gray-100 rounded-lg p-3 shadow-sm hover:shadow-md transition-all cursor-pointer group"
                                        onClick={() => setSelectedRubric(rubric)}
                                    >
                                        <div className="flex justify-between items-center mb-2">
                                            <span className="text-sm font-bold text-gray-800 group-hover:text-theme-primary transition-colors flex items-center gap-2">
                                                {rubric.rubric_name || (rubric as any).name || (rubric as any).criteria}
                                                <FaExpandAlt className="text-gray-300 group-hover:text-theme-primary text-xs opacity-0 group-hover:opacity-100 transition-opacity" />
                                            </span>
                                            <ScoreBar score={rubric.rating} />
                                        </div>

                                        {/* Truncated Analysis */}
                                        <p className="text-xs text-gray-500 line-clamp-2 leading-relaxed">
                                            {rubric.analysis || rubric.feedback}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>

            {/* Detail Modal */}
            <Modal
                isOpen={!!selectedRubric}
                onClose={() => setSelectedRubric(null)}
                title="評估詳情"
                maxWidth="max-w-5xl"
            >
                <div>
                    <div className="flex items-center justify-between mb-4 bg-gray-50 p-3 rounded-lg">
                        <span className="font-bold text-gray-700 text-lg">
                            {selectedRubric?.rubric_name || selectedRubric?.name || selectedRubric?.criteria || '評分'}
                        </span>
                        {selectedRubric && <ScoreBar score={selectedRubric.rating} showText={true} />}
                    </div>

                    <div className="mb-6">
                        <h4 className="text-sm font-bold text-gray-800 mb-2 border-l-4 border-theme-primary pl-2">分析說明</h4>
                        <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 leading-relaxed text-justify whitespace-pre-line">
                            {selectedRubric?.analysis || selectedRubric?.feedback}
                        </div>
                    </div>

                    {selectedRubric?.suggestions && selectedRubric.suggestions.length > 0 && (
                        <div>
                            <h4 className="text-sm font-bold text-gray-800 mb-2 border-l-4 border-yellow-400 pl-2">改進建議</h4>
                            <div className="bg-yellow-50 border border-yellow-100 rounded-lg p-4">
                                <ul className="space-y-2 list-disc list-inside text-sm text-gray-800">
                                    {selectedRubric.suggestions.map((s: string, i: number) => (
                                        <li key={i} className="leading-snug">{s}</li>
                                    ))}
                                </ul>
                            </div>
                        </div>
                    )}
                </div>
            </Modal>
        </>
    );
}
