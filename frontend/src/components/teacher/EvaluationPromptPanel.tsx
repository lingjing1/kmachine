import { useState } from 'react';
import { FaSpinner } from 'react-icons/fa';

interface EvaluationPromptPanelProps {
    onEvaluate: (workflow: 2 | 3 | 4) => Promise<void>;
    isEvaluating?: boolean;
    className?: string;
}

export default function EvaluationPromptPanel({
    onEvaluate,
    isEvaluating = false,
    className = ''
}: EvaluationPromptPanelProps) {
    const [selectedWorkflow, setSelectedWorkflow] = useState<2 | 3 | 4>(4);

    return (
        <div className={`bg-white flex flex-col p-6 h-full ${className}`}>
            <div className="pt-2"></div>

            {/* Workflow Selection */}
            <div className="mb-6">
                <label className="block text-sm font-semibold text-gray-700 mb-2">評估模式</label>
                <div className="space-y-2">
                    {[
                        { id: 2, label: '事實檢查', icon: '🎯', desc: '檢查生成結果是否根據參考資料事實', time: '~30秒' },
                        { id: 3, label: '教學品質查核', icon: '✨', desc: '確認生成結果是否符合您的教學目標', time: '~45秒' },
                        { id: 4, label: '完整評估', icon: '🔍', desc: '在生成結果符合參考資料時，進行教學品質查核', time: '~60秒', recommended: true }
                    ].map((mode) => (
                        <label
                            key={mode.id}
                            className={`cursor-pointer border-2 rounded-lg p-3 transition-all flex items-start gap-3 ${selectedWorkflow === mode.id
                                ? 'border-green-500 bg-green-50'
                                : 'border-gray-200 hover:border-gray-300'
                                }`}
                        >
                            <input
                                type="radio"
                                name="workflow"
                                value={mode.id}
                                checked={selectedWorkflow === mode.id}
                                onChange={() => setSelectedWorkflow(mode.id as 2 | 3 | 4)}
                                className="hidden"
                            />
                            <span className="text-2xl">{mode.icon}</span>
                            <div className="flex-1">
                                <div className="flex items-center gap-2">
                                    <span className={`font-semibold text-sm ${selectedWorkflow === mode.id ? 'text-green-700' : 'text-gray-700'
                                        }`}>
                                        {mode.label}
                                    </span>
                                    {mode.recommended && (
                                        <span className="text-[10px] bg-green-600 text-white px-1.5 py-0.5 rounded font-bold">
                                            推薦
                                        </span>
                                    )}
                                    <span className="text-[10px] text-gray-400 ml-auto">{mode.time}</span>
                                </div>
                                <div className="text-xs text-gray-500 mt-0.5">{mode.desc}</div>
                            </div>
                        </label>
                    ))}
                </div>
            </div>

            {/* Evaluate Button */}
            <button
                onClick={() => onEvaluate(selectedWorkflow)}
                disabled={isEvaluating}
                className="w-full py-3 px-4 bg-gradient-to-r from-green-500 to-teal-600 text-white font-bold rounded-lg hover:from-green-600 hover:to-teal-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-md hover:shadow-lg mb-6"
            >
                {isEvaluating ? (
                    <>
                        <FaSpinner className="animate-spin" />
                        <span>評估中...</span>
                    </>
                ) : (
                    <span>開始評估</span>
                )}
            </button>
        </div>
    );
}
