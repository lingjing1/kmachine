import React, { useState, useEffect } from 'react';
import { FaStar, FaEdit, FaChevronDown, FaChevronUp } from 'react-icons/fa';
import { submitMaterialRating, getMaterialRating, getMaterialRatingStats, MaterialRatingResponse } from '../../services/studentApi';

interface MaterialRatingModalProps {
  contentId?: number;     // Keeping for backward compatibility
  contentIds?: number[];  // New prop for batch mode
  isOpen: boolean;
  onClose: () => void;
  onSubmitSuccess?: () => void;
  onReturn?: () => void;
}

const MaterialRatingModal: React.FC<MaterialRatingModalProps> = ({
  contentId,
  contentIds = [],
  isOpen,
  onClose,
  onSubmitSuccess,
  onReturn
}) => {
  const isBatchMode = contentIds.length > 0;
  const targetId = isBatchMode ? contentIds[0] : (contentId || 0);
  const [rating, setRating] = useState<number>(0);
  const [hoverRating, setHoverRating] = useState<number>(0);
  const [feedback, setFeedback] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [existingRating, setExistingRating] = useState<MaterialRatingResponse | null>(null);
  const [isEditing, setIsEditing] = useState(false);
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

  // Detailed dimensions
  const [dimensions, setDimensions] = useState({
    clarity: 0,      // 內容易懂性
    engagement: 0,   // 學習吸引力
    difficulty: 0,   // 難易度適配
    structure: 0,    // 結構條理性
    helpfulness: 0   // 學習助益度
  });

  useEffect(() => {
    if (isOpen) {
      loadInitialData();
    }
  }, [isOpen, targetId]);

  const loadInitialData = async () => {
    try {
      setShowSuccess(false);

      // If batch mode, we skip loading existing ratings to avoid overwhelming the student
      // with old ratings. We just show a fresh rating form.
      if (isBatchMode) {
        setExistingRating(null);
        setRating(0);
        setFeedback('');
        setDimensions({ clarity: 0, engagement: 0, difficulty: 0, structure: 0, helpfulness: 0 });
        setIsEditing(true);

        // Still check if we should suggest detailed mode based on global stats
        const stats = await getMaterialRatingStats();
        setIsDetailed(stats.suggest_detailed);
        setIsForcedDetailed(stats.suggest_detailed);
        return;
      }

      // 1. Load existing rating (Single mode only)
      const existing = await getMaterialRating(targetId);
      if (existing) {
        setExistingRating(existing);
        setRating(existing.rating.score);
        setFeedback(existing.rating.feedback || '');
        setDimensions(existing.rating.dimensions as any || { clarity: 0, engagement: 0, difficulty: 0, structure: 0, helpfulness: 0 });
        setIsEditing(false);
        setIsDetailed(!!existing.rating.dimensions);
      } else {
        setExistingRating(null);
        setRating(0);
        setFeedback('');
        setDimensions({ clarity: 0, engagement: 0, difficulty: 0, structure: 0, helpfulness: 0 });
        setIsEditing(true);

        // 2. Check if we should suggest detailed mode
        const stats = await getMaterialRatingStats();
        setIsDetailed(stats.suggest_detailed);
        setIsForcedDetailed(stats.suggest_detailed);
      }
    } catch (err) {
      console.error('Failed to load initial rating data:', err);
    }
  };

  const handleSubmit = async () => {
    if (rating === 0) {
      setError('請選擇評分（1-5 星）');
      return;
    }

    if ((isDetailed || isForcedDetailed) && (
      dimensions.clarity === 0 ||
      dimensions.engagement === 0 ||
      dimensions.difficulty === 0 ||
      dimensions.structure === 0 ||
      dimensions.helpfulness === 0
    )) {
      setError('感謝您的鼓勵！請協助完成所有維度的評分，幫助我們持續優化');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);

      const ratingData = {
        rating,
        feedback: feedback.trim() || undefined,
        dimensions: isDetailed ? dimensions : undefined
      };

      if (isBatchMode) {
        const { batchSubmitMaterialRating } = await import('../../services/studentApi');
        await batchSubmitMaterialRating(contentIds, ratingData);
      } else {
        await submitMaterialRating(targetId, ratingData);
      }

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
          {/* Close button removed: rating is mandatory */}

          {showSuccess ? (
            <div className="flex flex-col items-center justify-center py-8 animate-in zoom-in duration-500">
              <div className="relative w-48 h-48 mb-6">
                <img
                  src={`/images/mascots/${randomMascot}`}
                  alt="Success Mascot"
                  className="w-full h-full object-contain drop-shadow-xl"
                />
              </div>
              <h3 className="text-2xl font-bold text-theme-primary mb-2">感謝您的回饋！</h3>
              <p className="text-neutral-text-secondary text-center leading-relaxed">
                我們已經收到您的回饋，<br />
                這將幫助我們持續優化教材品質，提供更好的學習體驗。
              </p>
              <div className="mt-8 flex gap-2">
                <div className="w-2 h-2 rounded-full bg-theme-primary animate-pulse"></div>
                <div className="w-2 h-2 rounded-full bg-theme-primary animate-pulse delay-75"></div>
                <div className="w-2 h-2 rounded-full bg-theme-primary animate-pulse delay-150"></div>
              </div>
            </div>
          ) : existingRating && !isEditing ? (
            // Show existing rating
            <div className="space-y-4">
              <div>
                <p className="text-sm text-neutral-text-secondary mb-2">您的評分</p>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((star) => (
                    <FaStar
                      key={star}
                      size={32}
                      className={star <= existingRating.rating.score ? 'text-yellow-400' : 'text-gray-300'}
                    />
                  ))}
                </div>
              </div>

              {existingRating.rating.dimensions && (
                <div className="bg-gray-50 rounded-xl p-4 space-y-3">
                  <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">詳細評估</p>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">內容易懂性</span>
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5].map(s => <FaStar key={s} size={14} className={s <= existingRating.rating.dimensions!.clarity ? 'text-yellow-400' : 'text-gray-200'} />)}
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">學習吸引力</span>
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5].map(s => <FaStar key={s} size={14} className={s <= existingRating.rating.dimensions!.engagement ? 'text-yellow-400' : 'text-gray-200'} />)}
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">難易度適配</span>
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5].map(s => <FaStar key={s} size={14} className={s <= existingRating.rating.dimensions!.difficulty ? 'text-yellow-400' : 'text-gray-200'} />)}
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">結構條理性</span>
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5].map(s => <FaStar key={s} size={14} className={s <= existingRating.rating.dimensions!.structure ? 'text-yellow-400' : 'text-gray-200'} />)}
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">學習助益度</span>
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5].map(s => <FaStar key={s} size={14} className={s <= existingRating.rating.dimensions!.helpfulness ? 'text-yellow-400' : 'text-gray-200'} />)}
                    </div>
                  </div>
                </div>
              )}

              {existingRating.rating.feedback && (
                <div>
                  <p className="text-sm text-neutral-text-secondary mb-2">您的回饋</p>
                  <div className="bg-gray-50 rounded-lg p-3 text-neutral-text-main italic text-sm border-l-4 border-gray-200">
                    "{existingRating.rating.feedback}"
                  </div>
                </div>
              )}

              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => setIsEditing(true)}
                  className="flex-1 px-4 py-3 rounded-xl font-semibold text-blue-600 bg-blue-50 hover:bg-blue-100 transition-all flex items-center justify-center gap-2"
                >
                  <FaEdit size={16} />
                  重新評分
                </button>
                <button
                  onClick={onReturn || onClose}
                  className="flex-1 px-4 py-3 rounded-xl font-semibold text-white bg-theme-primary hover:bg-blue-600 transition-all"
                >
                  關閉
                </button>
              </div>
            </div>
          ) : (
            // Rating form
            <div className="space-y-6">
              {/* Star Rating */}
              <div>
                <label className="block text-sm font-medium text-neutral-text-secondary mb-3">
                  這份教材是否能有效引導您掌握學習重點? *
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

              {/* Detailed Toggle */}
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
                    {isDetailed ? '收起詳細評分' : '顯示詳細評分 (選填)'}
                  </button>
                )}

                {(isDetailed || isForcedDetailed) && (
                  <div className="mt-4 space-y-4 bg-gray-50 rounded-2xl p-4 animate-in fade-in slide-in-from-top-2 duration-300">
                    <div className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">此份教材的說明是否清晰易懂，有助於您快速掌握核心重點？</span>
                        <span className="text-xs text-gray-400">{dimensions.clarity || 0}/5</span>
                      </div>
                      {renderStarsList(dimensions.clarity, (v) => handleDimensionChange('clarity', v), 24)}
                    </div>

                    <div className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">教材中的學習情境與範例，是否吸引您閱讀完此份教材？</span>
                        <span className="text-xs text-gray-400">{dimensions.engagement || 0}/5</span>
                      </div>
                      {renderStarsList(dimensions.engagement, (v) => handleDimensionChange('engagement', v), 24)}
                    </div>

                    <div className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">教材的難易度是否符合您的學習進度？</span>
                        <span className="text-xs text-gray-400">{dimensions.difficulty || 0}/5</span>
                      </div>
                      {renderStarsList(dimensions.difficulty, (v) => handleDimensionChange('difficulty', v), 24)}
                    </div>

                    <div className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">教材的大綱編排是否能有效引導您循序漸進地完成學習？</span>
                        <span className="text-xs text-gray-400">{dimensions.structure || 0}/5</span>
                      </div>
                      {renderStarsList(dimensions.structure, (v) => handleDimensionChange('structure', v), 24)}
                    </div>

                    <div className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-gray-700">此份教材是否有助於你解答疑惑，或對該主題有更深層的理解？</span>
                        <span className="text-xs text-gray-400">{dimensions.helpfulness || 0}/5</span>
                      </div>
                      {renderStarsList(dimensions.helpfulness, (v) => handleDimensionChange('helpfulness', v), 24)}
                    </div>
                  </div>
                )}
              </div>

              {/* Feedback Textarea */}
              <div>
                <label className="block text-sm font-medium text-neutral-text-secondary mb-2">
                  更多心得或具體回饋 (選填)
                </label>
                <textarea
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  placeholder="您的具體回饋（例如：教材內容是否清楚、難度是否適中等）將幫助我們持續優化教材品質..."
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
              <div className="flex gap-3">
                <button
                  onClick={handleSubmit}
                  disabled={isSubmitting || rating === 0}
                  className={`flex-1 px-4 py-3 rounded-xl font-semibold text-white transition-all ${isSubmitting || rating === 0
                    ? 'bg-gray-300 cursor-not-allowed'
                    : 'bg-theme-primary hover:bg-blue-600 hover:shadow-lg active:scale-95'
                    }`}
                >
                  {isSubmitting ? '提交中...' : '提交評分'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MaterialRatingModal;
