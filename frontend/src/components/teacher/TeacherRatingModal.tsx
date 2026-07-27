import React, { useState, useEffect } from 'react';
import { FaStar, FaChevronDown, FaChevronUp } from 'react-icons/fa';
import { submitTeacherRating, getTeacherRatingStats } from '../../services/teacherRatingApi';

interface TeacherRatingModalProps {
    contentId: number;
    isOpen: boolean;
    onClose: () => void;
    onSubmitSuccess?: () => void;
    isRegeneration?: boolean;
}

const TeacherRatingModal: React.FC<TeacherRatingModalProps> = ({
    contentId,
    isOpen,
    onClose,
    onSubmitSuccess,
    isRegeneration = false
}) => {
    const [rating, setRating] = useState<number>(0);
    const [hoverRating, setHoverRating] = useState<number>(0);
    const [feedback, setFeedback] = useState<string>('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isDetailed, setIsDetailed] = useState(false);
    const [isForcedDetailed, setIsForcedDetailed] = useState(false);
    const [showSuccess, setShowSuccess] = useState(false);
    const [randomMascot, setRandomMascot] = useState('');

    const mascots = [
        'fill_in_blank.png',
        'planner.png',
        'quiz_master.png',
        'retriever.png',
        'short_answer.png',
        'summarizer.png',
        'true_false.png'
    ];

    // Teacher dimensions
    const [dimensions, setDimensions] = useState({
        faithfulness: 0,   // 引用正確性 (ragas_faithfulness)
        focus: 0,          // 核心聚焦 (Core Concept Focus)
        phrasing: 0,       // 措辭通順 (Grammatical & Phrasing)
        understandable: 0, // 學生理解 (Understandable)
        logic: 0,          // 邏輯一致 (Logical_Consistency)
        critic: 0,         // 評估引導 (AI Critic Feedback)
        efficiency: 0      // 備課效益 (Efficiency)
    });

    useEffect(() => {
        if (isOpen) {
            loadInitialData();
        }
    }, [isOpen, contentId]);

    const loadInitialData = async () => {
        try {
            setRating(0);
            setFeedback('');
            setShowSuccess(false);
            setDimensions({
                faithfulness: 0, focus: 0, phrasing: 0, understandable: 0,
                logic: 0, critic: 0, efficiency: 0
            });

            // Check if we should suggest detailed mode
            const stats = await getTeacherRatingStats();
            setIsDetailed(stats.suggest_detailed);
            setIsForcedDetailed(stats.suggest_detailed);
        } catch (err) {
            console.error('Failed to load rating stats:', err);
        }
    };

    const handleSubmit = async () => {
        if (rating === 0) {
            setError('請選擇評分（1-5 星）');
            return;
        }

        if (isRegeneration && !feedback.trim()) {
            setError('十分抱歉教材品質欠佳! 請詳細描述您本次遇到的問題(如: 未按照我的指令、生成內容不完整...)，讓我們變得更好');
            return;
        }

        if (isDetailed && !isRegeneration && (
            dimensions.faithfulness === 0 ||
            dimensions.focus === 0 ||
            dimensions.phrasing === 0 ||
            dimensions.understandable === 0 ||
            dimensions.logic === 0 ||
            dimensions.critic === 0 ||
            dimensions.efficiency === 0
        )) {
            setError('感謝您的使用！請協助完成所有維度的評分，讓我們變得更好');
            return;
        }

        try {
            setIsSubmitting(true);
            setError(null);
            await submitTeacherRating(contentId, {
                rating,
                feedback: feedback.trim() || undefined,
                dimensions: isDetailed ? dimensions : undefined
            });

            // Show success mascot
            const mascot = mascots[Math.floor(Math.random() * mascots.length)];
            setRandomMascot(mascot);
            setShowSuccess(true);

            // Wait 3 seconds then signal success
            setTimeout(() => {
                if (onSubmitSuccess) {
                    onSubmitSuccess();
                } else {
                    onClose();
                }
                setShowSuccess(false);
            }, 3000);
        } catch (err: any) {
            setError(err.message || '提交失敗，請稍後再試');
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleDimensionChange = (dim: keyof typeof dimensions, value: number) => {
        setDimensions(prev => ({ ...prev, [dim]: value }));
    };

    if (!isOpen) return null;

    const renderStarsList = (current: number, setter: (val: number) => void, size = 32) => (
        <div className="flex gap-1 justify-start">
            {[1, 2, 3, 4, 5].map((star) => (
                <button
                    key={star}
                    type="button"
                    onClick={() => setter(star)}
                    className="transition-transform hover:scale-110"
                >
                    <FaStar
                        size={size}
                        className={star <= current ? 'text-yellow-400' : 'text-gray-300'}
                    />
                </button>
            ))}
        </div>
    );

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full relative max-h-[90vh] flex flex-col overflow-hidden">
                <div className="overflow-y-auto p-6 custom-scrollbar">
                    {/* Close button removed for focus on feedback */}

                    {showSuccess ? (
                        <div className="flex flex-col items-center justify-center py-8 animate-in zoom-in duration-500">
                            <div className="relative w-48 h-48 mb-6">
                                <img
                                    src={`/images/mascots/${randomMascot}`}
                                    alt="Success Mascot"
                                    className="w-full h-full object-contain drop-shadow-xl"
                                />
                            </div>
                            <h3 className="text-2xl font-bold text-theme-primary mb-2">感謝您的建議！</h3>
                            <p className="text-neutral-text-secondary text-center leading-relaxed">
                                老師您辛苦了！我們已收到您的專業意見，<br />
                                我們將持續優化系統，為您提供更優質的備課支援。
                            </p>
                            <div className="mt-8 flex gap-2">
                                <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></div>
                                <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse delay-75"></div>
                                <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse delay-150"></div>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {/* Title */}
                            <div>
                                <h3 className="text-2xl font-bold text-neutral-text-main">
                                    {isRegeneration ? '重新生成回饋' : '生成品質評分'}
                                </h3>
                                <p className="text-sm text-neutral-text-secondary mt-1">
                                    {isRegeneration ? '請告訴我們為什麼您需要重新生成，這將幫助 AI 持續優化' : '您的回饋將幫助 AI 持續優化生成結果'}
                                </p>
                            </div>

                            {/* Rating form */}
                            <div className="space-y-6">
                                {/* Star Rating */}
                                <div>
                                    <label className="block text-sm font-medium text-neutral-text-secondary mb-3">
                                        {isRegeneration ? '您對此份教材的滿意度如何？ *' : '整體生成品質滿意度 *'}
                                    </label>
                                    <div className="flex gap-2 justify-start">
                                        {[1, 2, 3, 4, 5].map((star) => (
                                            <button
                                                key={star}
                                                type="button"
                                                onClick={() => setRating(star)}
                                                onMouseEnter={() => setHoverRating(star)}
                                                onMouseLeave={() => setHoverRating(0)}
                                                className="transition-transform hover:scale-110"
                                            >
                                                <FaStar
                                                    size={40}
                                                    className={
                                                        star <= (hoverRating || rating)
                                                            ? 'text-yellow-400'
                                                            : 'text-gray-300'
                                                    }
                                                />
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* Detailed Toggle - Only show if not regeneration or if manually enabled */}
                                {!isRegeneration && (
                                    <div className="border-t border-neutral-border pt-4">
                                        {isForcedDetailed ? (
                                            <div className="flex items-center gap-2 text-sm text-theme-primary font-bold mb-2">
                                                <FaStar size={12} className="text-yellow-400" />
                                                <span>詳細滿意度調查</span>
                                            </div>
                                        ) : (
                                            <button
                                                type="button"
                                                onClick={() => setIsDetailed(!isDetailed)}
                                                className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700 font-medium transition-colors"
                                            >
                                                {isDetailed ? <FaChevronUp size={12} /> : <FaChevronDown size={12} />}
                                                {isDetailed ? '收起詳細評分' : '顯示詳細評估 (選填)'}
                                            </button>
                                        )}

                                        {(isDetailed || isForcedDetailed) && (
                                            <div className="mt-4 space-y-4 bg-gray-50 rounded-2xl p-4 animate-in fade-in slide-in-from-top-2 duration-300">
                                                {/* 1. Faithfulness */}
                                                <div className="space-y-2">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-sm font-medium text-gray-700">此份教材的內容是否正確引用了您選擇的參考資料？</span>
                                                        <span className="text-xs text-gray-400">{dimensions.faithfulness || 0}/5</span>
                                                    </div>
                                                    {renderStarsList(dimensions.faithfulness, (v) => handleDimensionChange('faithfulness', v), 24)}
                                                </div>

                                                {/* 2. Concept Focus */}
                                                <div className="space-y-2">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-sm font-medium text-gray-700">此份教材是否契合您的教學目標，並正確聚焦於核心概念(您選擇的知識點)？</span>
                                                        <span className="text-xs text-gray-400">{dimensions.focus || 0}/5</span>
                                                    </div>
                                                    {renderStarsList(dimensions.focus, (v) => handleDimensionChange('focus', v), 24)}
                                                </div>

                                                {/* 3. Phrasing */}
                                                <div className="space-y-2">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-sm font-medium text-gray-700">此份教材的語句是否流暢自然，感覺像人類編寫而非 AI 生成？</span>
                                                        <span className="text-xs text-gray-400">{dimensions.phrasing || 0}/5</span>
                                                    </div>
                                                    {renderStarsList(dimensions.phrasing, (v) => handleDimensionChange('phrasing', v), 24)}
                                                </div>

                                                {/* 4. Understandable */}
                                                <div className="space-y-2">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-sm font-medium text-gray-700">此份教材的情境與難易度是否適合學生理解？</span>
                                                        <span className="text-xs text-gray-400">{dimensions.understandable || 0}/5</span>
                                                    </div>
                                                    {renderStarsList(dimensions.understandable, (v) => handleDimensionChange('understandable', v), 24)}
                                                </div>

                                                {/* 5. Logic */}
                                                <div className="space-y-2">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-sm font-medium text-gray-700">此份教材的內容是否邏輯嚴謹，且答案準確無誤？</span>
                                                        <span className="text-xs text-gray-400">{dimensions.logic || 0}/5</span>
                                                    </div>
                                                    {renderStarsList(dimensions.logic, (v) => handleDimensionChange('logic', v), 24)}
                                                </div>

                                                {/* 6. Critic */}
                                                <div className="space-y-2">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-sm font-medium text-gray-700">AI 自動評估的修改建議，是否有助於您優化教材品質？</span>
                                                        <span className="text-xs text-gray-400">{dimensions.critic || 0}/5</span>
                                                    </div>
                                                    {renderStarsList(dimensions.critic, (v) => handleDimensionChange('critic', v), 24)}
                                                </div>

                                                {/* 7. Efficiency */}
                                                <div className="space-y-2">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-sm font-medium text-gray-700">本次生成與編修過程，是否有幫助您節省備課時間？</span>
                                                        <span className="text-xs text-gray-400">{dimensions.efficiency || 0}/5</span>
                                                    </div>
                                                    {renderStarsList(dimensions.efficiency, (v) => handleDimensionChange('efficiency', v), 24)}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Feedback Textarea */}
                                <div>
                                    <label className="block text-sm font-medium text-neutral-text-secondary mb-2">
                                        {isRegeneration ? '具體問題描述 *' : '具體改進建議 (選填)'}
                                    </label>
                                    <textarea
                                        value={feedback}
                                        onChange={(e) => setFeedback(e.target.value)}
                                        placeholder={isRegeneration ? '請描述您遇到的問題，例如：內容不正確、長度不足、不符合教學目標...' : '例如：內容太難、格式不對、或者是哪裡有錯誤...'}
                                        className="w-full px-4 py-3 rounded-xl border border-neutral-border focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-blue-400 resize-none transition-all text-sm"
                                        rows={3}
                                        maxLength={500}
                                    />
                                </div>

                                {/* Error Message */}
                                {error && (
                                    <div className="text-red-500 bg-red-50 p-3 rounded-xl text-xs flex items-center gap-2 border border-red-100">
                                        <span>⚠️</span> {error}
                                    </div>
                                )}

                                {/* Submit Button */}
                                <div>
                                    <button
                                        onClick={handleSubmit}
                                        disabled={isSubmitting || rating === 0}
                                        className={`w-full px-4 py-4 rounded-xl font-bold text-white transition-all shadow-md ${isSubmitting || rating === 0
                                            ? 'bg-gray-300 cursor-not-allowed'
                                            : 'bg-theme-primary hover:bg-blue-600 hover:shadow-lg active:scale-95'
                                            }`}
                                    >
                                        {isSubmitting ? '提交中...' : '送出回饋'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default TeacherRatingModal;
