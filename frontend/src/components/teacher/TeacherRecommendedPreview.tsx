import React, { useState, useEffect } from 'react';
import { getRecommendedQuestions, RecommendedQuestionItem } from '../../services/studentApi';
import { ExamContentView } from '../reports/ExamContentView';
import { FaSpinner, FaSyncAlt } from 'react-icons/fa';
import { MdQuiz } from 'react-icons/md';

interface TeacherRecommendedPreviewProps {
    knowledgePointIds: number[];
    courseId?: number | string;
    stage: 'preview' | 'review';
    countPerKp?: number;
    totalMax?: number;
    totalQuestions?: number;
    kpsWithQuestions?: number;
    enabled?: boolean;
    onConfigChange?: (config: { count_per_kp?: number; total_max?: number; enabled?: boolean }) => void;
    onKPLookup?: (kpName: string) => void;
}

const TeacherRecommendedPreview: React.FC<TeacherRecommendedPreviewProps> = ({
    knowledgePointIds,
    courseId,
    stage: _stage,
    countPerKp = 1,
    totalMax = 5,
    totalQuestions = 0,
    kpsWithQuestions = 0,
    enabled = true,
    onConfigChange,
    onKPLookup
}) => {
    const [questions, setQuestions] = useState<RecommendedQuestionItem[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [hasPreviewed, setHasPreviewed] = useState(false);

    const fetchQuestions = async () => {
        if (!knowledgePointIds || knowledgePointIds.length === 0) {
            setIsLoading(false);
            return;
        }

        try {
            setIsLoading(true);

            const response = await getRecommendedQuestions(knowledgePointIds, courseId, {
                question_type: 'short_answer',
                count_per_kp: countPerKp,
                total_max: totalMax
            });

            setQuestions(response.questions);
            setHasPreviewed(true);
        } catch (err: any) {
            console.error('Failed to fetch recommended questions:', err);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        // Reset preview state when KPs change significantly
        if (hasPreviewed) {
            setHasPreviewed(false);
            setQuestions([]);
        }
    }, [JSON.stringify(knowledgePointIds)]);

    if (knowledgePointIds.length === 0) {
        return null;
    }

    return (
        <div className="space-y-6">
            {/* Config Panel - Always Visible */}
            <div className="rounded-xl py-6">
                <div className="flex items-center gap-3 mb-6">
                    <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 shadow-sm">
                        <MdQuiz size={20} />
                    </div>
                    <div className="flex-1">
                        <h3 className="text-lg font-bold text-gray-800">基於知識點智慧推薦題目</h3>
                        <p className="text-sm text-gray-500 mt-0.5">
                            設定系統如何根據本教材知識點自動抽取題目
                            {totalQuestions > 0 ? (
                                <span className="ml-1 text-blue-600 font-medium">
                                    ({kpsWithQuestions} 個知識點有題目，共 {totalQuestions} 題)
                                </span>
                            ) : (
                                <span className="ml-1 text-gray-400">(目前連結的知識點尚無題目)</span>
                            )}
                        </p>
                    </div>
                    {/* Enable/Disable Toggle - right of the whole text block */}
                    <div className="flex items-center gap-2 shrink-0">
                        <span className={`text-xs font-medium ${enabled ? 'text-blue-600' : 'text-gray-400'}`}>
                            {enabled ? '開啟' : '關閉'}
                        </span>
                        <button
                            onClick={() => onConfigChange?.({ enabled: !enabled })}
                            className={`relative inline-flex h-7 w-14 items-center rounded-full transition-colors focus:outline-none ${enabled ? 'bg-blue-500' : 'bg-gray-300'
                                }`}
                            title={enabled ? '點擊關閉智慧推薦' : '點擊開啟智慧推薦'}
                        >
                            <span
                                className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${enabled ? 'translate-x-8' : 'translate-x-1'
                                    }`}
                            />
                        </button>
                    </div>
                </div>

                <div className={`flex flex-col md:flex-row md:items-end justify-between gap-8 transition-opacity ${enabled ? 'opacity-100' : 'opacity-40 pointer-events-none'
                    }`}>
                    <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-8">
                        <div className="space-y-3">
                            <label className="text-sm font-bold text-gray-700 flex items-center gap-2">
                                總抽取題數
                                <span className="text-[10px] bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full">最多 10 題</span>
                            </label>
                            <div className="flex items-center gap-4">
                                <input
                                    type="range"
                                    min="1"
                                    max="10"
                                    value={totalMax}
                                    onChange={(e) => {
                                        const val = parseInt(e.target.value);
                                        onConfigChange?.({ total_max: val });
                                    }}
                                    className="flex-1 h-2 bg-blue-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                                />
                                <span className="w-12 text-center font-bold text-blue-700 bg-white border-2 border-blue-200 rounded-lg py-1.5 text-sm shadow-sm">
                                    {totalMax}
                                </span>
                            </div>
                        </div>
                        <div className="space-y-3">
                            <label className="text-sm font-bold text-gray-700 flex items-center gap-2">
                                每個知識點抽題數
                                <span className="text-[10px] bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full">最多 3 題</span>
                            </label>
                            <div className="flex items-center gap-4">
                                <input
                                    type="range"
                                    min="1"
                                    max="3"
                                    value={countPerKp}
                                    onChange={(e) => {
                                        const val = parseInt(e.target.value);
                                        onConfigChange?.({ count_per_kp: val });
                                    }}
                                    className="flex-1 h-2 bg-blue-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                                />
                                <span className="w-12 text-center font-bold text-blue-700 bg-white border-2 border-blue-200 rounded-lg py-1.5 text-sm shadow-sm">
                                    {countPerKp}
                                </span>
                            </div>
                        </div>
                    </div>

                    <div className="flex-shrink-0">
                        <button
                            onClick={fetchQuestions}
                            disabled={isLoading}
                            className={`flex items-center gap-1.5 px-4 py-2 rounded-full bg-blue-50 text-blue-600 border border-blue-200 text-sm font-semibold hover:bg-blue-100 transition-colors ${isLoading ? 'opacity-50 cursor-not-allowed' : ''
                                }`}
                        >
                            {isLoading ? (
                                <FaSpinner className="animate-spin" size={13} />
                            ) : (
                                <FaSyncAlt size={12} />
                            )}
                            預覽學生端推薦題目
                        </button>
                    </div>
                </div>
            </div>

            {/* Questions List - Only visible after preview */}
            {hasPreviewed && (
                <div className="space-y-6 animate-in fade-in slide-in-from-top-4 duration-500">
                    <div className="flex items-center gap-2 px-2 text-gray-400">
                        <div className="h-[1px] flex-1 bg-gray-100"></div>
                        <span className="text-xs font-medium uppercase tracking-wider">以下為智慧推薦題目預覽</span>
                        <div className="h-[1px] flex-1 bg-gray-100"></div>
                    </div>

                    {questions.length > 0 ? (
                        <div className="space-y-6">
                            {questions.map((q, idx) => {
                                const mappedQuestion = {
                                    id: q.id,
                                    question_text: q.question, // Backend RecommendedQuestionItem uses 'question'
                                    options: q.options,
                                    correct_answer: q.correct_answer,
                                    sample_answer: q.sample_answer || q.answer,
                                    detailed_explanation: q.detailed_explanation,
                                    type: q.question_type,
                                    related_kps: [q.knowledge_point_name],
                                    source: q.source,
                                    tags: q.tags // Pass tags
                                };

                                return (
                                    <ExamContentView
                                        key={q.id}
                                        question={mappedQuestion}
                                        index={idx}
                                        displayNumber={idx + 1}
                                        editable={false}
                                        isEditing={false}
                                        onStartEdit={() => { }}
                                        onSaveEdit={() => { }}
                                        onCancelEdit={() => { }}
                                        onTempChange={() => { }}
                                        onKPLookup={onKPLookup}
                                        isFirstItem={idx === 0}
                                        isLastItem={idx === questions.length - 1}
                                    />
                                );
                            })}
                        </div>
                    ) : (
                        <div className="py-12 text-center bg-gray-50 rounded-2xl border-2 border-dashed border-gray-100 px-6">
                            {(courseId?.toString() === '3' || courseId?.toString() === '62') ? (
                                <p className="text-gray-400">
                                    此為實驗課程，當前知識點下找不到符合條件的題目，<br />
                                    請確認是否有非 AI 生成的題目或嘗試調整配置。
                                </p>
                            ) : (
                                <p className="text-gray-400">當前知識點下找不到符合條件的題目，請嘗試調整配置。</p>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default TeacherRecommendedPreview;
