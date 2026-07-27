import React, { useState } from 'react';
import { FaCheck, FaTimes, FaArrowUp, FaArrowDown, FaPen, FaTrash, FaStar, FaRegStar, FaLink, FaLightbulb, FaChevronDown, FaSearch, FaPlus } from 'react-icons/fa';
import { FaCheckToSlot } from 'react-icons/fa6';
import { RiMarkPenFill } from 'react-icons/ri';
import ReactMarkdown from 'react-markdown';
import { GradingConfig } from '../../utils/grading';

interface ExamContentViewProps {
  question: any;
  index: number;
  displayNumber: number | null;

  // 編輯模式控制
  editable: boolean;
  isEditing: boolean;
  tempQuestion?: any;

  // 編輯操作
  onStartEdit: (index: number, question: any) => void;
  onSaveEdit: (index: number) => void;
  onCancelEdit: () => void;
  onTempChange: (field: string, value: any) => void;
  onTempOptionChange?: (key: string, value: string) => void;

  // 題目操作
  onMoveUp?: (index: number) => void;
  onMoveDown?: (index: number) => void;
  onDelete?: (index: number) => void;

  // 題庫操作
  onAddToBank?: (index: number, question: any) => void;
  onRemoveFromBank?: (index: number, id: number) => void;
  onEditBankQuestion?: (index: number, question: any) => void;

  // 配分相關
  gradingConfig?: GradingConfig;
  onScoreChange?: (index: number, newScore: number) => void;

  // 引用相關
  onReferenceClick?: (chunkId: number | string, evidence: string, matchScore?: number, fullChunk?: any, questionId?: number, refType?: 'question' | 'section') => void;

  // Focus 控制 (Unused - keeping in interface if needed by parent but commenting out to fix lint)
  // focusIndex?: number | null;
  // autoEditIndex?: number | null;

  // 其他控制
  isFirstItem?: boolean;
  isLastItem?: boolean;
  availableKPs?: { id: string | number; name: string; category?: string; source_name?: string }[];
  onKPLookup?: (kpName: string) => void;
  onAddKP?: (name: string) => Promise<{ id: string | number; name: string } | null>;
}

export const ExamContentView: React.FC<ExamContentViewProps> = ({
  question,
  index,
  displayNumber,
  editable,
  isEditing,
  tempQuestion,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onTempChange,
  onTempOptionChange,
  onMoveUp,
  onMoveDown,
  onDelete,
  onAddToBank,
  onRemoveFromBank,
  onEditBankQuestion,
  gradingConfig,
  onScoreChange,
  onReferenceClick,
  // focusIndex,
  // autoEditIndex,
  isFirstItem = false,
  isLastItem = false,
  availableKPs = [] as { id: string | number; name: string; category?: string; source_name?: string }[],
  onKPLookup,
  onAddKP,
}) => {
  const [showKPSelector, setShowKPSelector] = useState(false);
  const [newKPName, setNewKPName] = useState('');
  const [isAddingKP, setIsAddingKP] = useState(false);
  const currentQ = isEditing ? tempQuestion : question;

  // [NEW] Group KPs by Category for Better UX
  const groupedKPs = availableKPs.reduce((acc, kp) => {
    // Priority: Group by source_name if available (and not manual), otherwise fall back to category
    const groupKey = (kp.source_name && kp.source_name !== '手動新增')
      ? `source:${kp.source_name}`
      : (kp.category || 'other');

    if (!acc[groupKey]) acc[groupKey] = [];
    acc[groupKey].push(kp);
    return acc;
  }, {} as Record<string, typeof availableKPs>);

  const categoryLabels: Record<string, string> = {
    'unit': '單元知識點',
    'extracted': '從參考資料提取',
    'course': '其他課程知識點',
    'other': '其他'
  };


  const handleAddNewKP = async () => {
    if (!newKPName.trim() || !onAddKP) return;
    setIsAddingKP(true);
    try {
      const result = await onAddKP(newKPName.trim());
      if (result) {
        onTempChange('related_kps', [result.name]);
        onTempChange('kp_id', result.id);
        setNewKPName('');
        setShowKPSelector(false);
      }
    } catch (err) {
      console.error("Failed to add KP", err);
    } finally {
      setIsAddingKP(false);
    }
  };

  // Determine type label and color
  const type = currentQ.type || currentQ.question_type || 'unknown';
  const typeLabel = type === 'multiple_choice' ? '選擇題' :
    type === 'short_answer' ? '簡答題' :
      type === 'true_false' ? '是非題' :
        type === 'fill_in_blank' || type === 'fill_in_the_blank' ? '填空題' : '題目';


  return (
    <div
      id={`question-item-${index}`}
      data-index={index}
      data-question-id={displayNumber}
      className={`bg-white p-6 rounded-xl border shadow-sm group transition-all duration-300 relative ${isEditing
        ? 'border-theme-primary ring-2 ring-theme-primary/10'
        : 'border-neutral-border hover:shadow-md hover:-translate-y-0.5'
        }`}
    >
      {/* Related KPs & Toolbar moved inside Content Area below for better flow */}

      <div className="flex items-start gap-4">
        {/* Question Number & Type Tag Column */}
        <div className="flex flex-col items-center gap-0.5 shrink-0 w-16 pt-0.5 mr-2">
          <span className="text-2xl font-bold text-blue-800 font-mono leading-none">
            {displayNumber ? String(displayNumber).padStart(2, '0') : '#'}
          </span>
          <span className="text-[10px] text-gray-400 font-medium whitespace-nowrap overflow-hidden text-ellipsis w-full text-center">
            {typeLabel}
          </span>

          {/* Tags */}
          {currentQ.tags && currentQ.tags.length > 0 && (
            <div className="mt-1.5 flex flex-col items-center gap-1 w-full overflow-hidden">
              {currentQ.tags.map((tag: string, tidx: number) => (
                <span
                  key={tidx}
                  className={`text-[8.5px] px-1 py-0.5 rounded leading-none w-full text-center truncate ${tag === 'AI生成'
                    ? 'bg-purple-50 text-purple-600 border border-purple-100 font-bold'
                    : tag === '手動新增'
                      ? 'bg-blue-50 text-blue-600 border border-blue-100'
                      : 'bg-gray-50 text-gray-500 border border-gray-100'
                    }`}
                  title={tag}
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* Grading Input */}
          {gradingConfig && displayNumber && (
            <div className="mt-1 flex flex-col items-center">
              <div className="relative">
                <input
                  type="number"
                  min="0"
                  className={`w-14 text-center text-sm font-bold border rounded py-1 px-1 focus:outline-none focus:ring-1 focus:ring-theme-primary ${gradingConfig.grading_method === 'by_individual_question'
                    ? 'bg-white border-gray-300 text-neutral-text-main'
                    : 'bg-gray-50 border-gray-200 text-gray-500'
                    }`}
                  value={
                    gradingConfig.grading_method === 'by_individual_question'
                      ? (gradingConfig.individual_questions?.[displayNumber - 1]?.points || 0)
                      : (gradingConfig.question_types.find((t: any) => t.type_id === type)?.points_per_question || 0)
                  }
                  onChange={(e) => {
                    if (onScoreChange) {
                      onScoreChange(displayNumber - 1, Number(e.target.value));
                    }
                  }}
                  disabled={gradingConfig.grading_method !== 'by_individual_question'}
                  title={gradingConfig.grading_method !== 'by_individual_question' ? "請切換至「每題配分」模式以修改個別分數" : "修改此題分數"}
                />
                <span className="absolute -right-4 top-1.5 text-xs text-gray-400 font-bold scale-75">分</span>
              </div>
            </div>
          )}
        </div>

        {/* Content Area */}
        <div className="flex-1 pr-2 border-l border-gray-100 pl-4 relative">
          {/* Header Bar: KP Badge/Selector & Actions */}
          <div className="flex items-start justify-between gap-4 mb-3">
            {/* Knowledge Points */}
            <div className="flex-1 min-w-0">
              {(currentQ.related_kps?.length > 0 || isEditing) && (
                <div className="flex flex-wrap gap-2">
                  {isEditing ? (
                    <div className="relative w-full max-w-[320px]">
                      <button
                        onClick={() => setShowKPSelector(!showKPSelector)}
                        className="w-full flex items-center justify-between gap-1.5 px-2.5 py-1.5 text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200 rounded-lg hover:bg-amber-100 transition-all group/kp shadow-sm overflow-hidden"
                      >
                        <div className="flex items-center gap-2 truncate">
                          <FaLightbulb className="text-amber-500 shrink-0" size={12} />
                          <span className="truncate">
                            {currentQ.related_kps?.[0] || '選擇知識點...'}
                          </span>
                        </div>
                        <FaChevronDown className={`text-amber-400 text-[10px] shrink-0 transition-transform duration-200 ${showKPSelector ? 'rotate-180' : ''}`} />
                      </button>

                      {/* Custom Amber Dropdown */}
                      {showKPSelector && (
                        <div className="absolute top-full left-0 w-[400px] mt-1 bg-white border border-amber-100 rounded-xl shadow-2xl z-50 flex flex-col max-h-[18rem] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                          <div className="p-2 border-b border-amber-100 flex justify-between items-center bg-amber-50/30 shrink-0">
                            <span className="text-[10px] font-bold text-amber-700 uppercase tracking-widest">可選知識點</span>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => {
                                  onTempChange('related_kps', []);
                                  onTempChange('kp_id', null);
                                  setShowKPSelector(false);
                                }}
                                className="bg-amber-500 hover:bg-amber-600 text-white px-2 py-0.5 rounded text-[10px] font-bold shadow-sm transition-all"
                              >
                                清除選擇
                              </button>
                              <button
                                onClick={() => setShowKPSelector(false)}
                                className="text-amber-400 hover:text-amber-600 p-1 hover:bg-amber-100 rounded transition-colors"
                              >
                                <FaTimes size={10} />
                              </button>
                            </div>
                          </div>

                          {/* Manual Add KP Section - Moved to Top */}
                          {onAddKP && (
                            <div className="p-2 border-b border-amber-100 bg-amber-50/20 shrink-0">
                              <div className="flex gap-1">
                                <input
                                  type="text"
                                  value={newKPName}
                                  onChange={(e) => setNewKPName(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' && newKPName.trim() && !isAddingKP) {
                                      e.preventDefault();
                                      handleAddNewKP();
                                    }
                                  }}
                                  placeholder="手動新增知識點..."
                                  className="flex-1 px-2 py-1.5 text-xs bg-white border border-amber-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-400 transition-all font-medium text-amber-900"
                                />
                                <button
                                  onClick={handleAddNewKP}
                                  disabled={!newKPName.trim() || isAddingKP}
                                  className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 text-white rounded-lg text-xs font-bold shadow-sm transition-all active:scale-95"
                                >
                                  {isAddingKP ? <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <FaPlus size={10} />}
                                </button>
                              </div>
                            </div>
                          )}

                          <div className="flex-1 overflow-y-auto custom-scrollbar">
                            {Object.keys(groupedKPs).sort((a, b) => {
                              // Define sort order: extracted sources first, then unit, then others
                              const rank = (s: string) => {
                                if (s.startsWith('source:')) return 0;
                                if (s === 'unit') return 1;
                                if (s === 'course') return 2;
                                return 3;
                              };
                              return rank(a) - rank(b);
                            }).map(groupKey => {
                              const kps = groupedKPs[groupKey];
                              if (!kps || kps.length === 0) return null;

                              // Determine display label
                              let displayLabel = categoryLabels[groupKey] || groupKey;
                              if (groupKey.startsWith('source:')) {
                                displayLabel = `來源：${groupKey.replace('source:', '')}`;
                              }

                              return (
                                <div key={groupKey} className="bg-white">
                                  <div className="px-3 py-1.5 bg-gray-50 border-y border-gray-100/50 sticky top-0 z-10 backdrop-blur-sm">
                                    <span className="text-[10px] font-bold text-gray-500 flex items-center gap-1.5">
                                      <div className="w-1 h-3 bg-amber-400 rounded-full"></div>
                                      {displayLabel}
                                    </span>
                                  </div>
                                  <div className="grid grid-cols-2 gap-px bg-amber-50/10">
                                    {kps.map((kp, kpIdx) => (
                                      <button
                                        key={kp.id}
                                        onClick={() => {
                                          onTempChange('related_kps', [kp.name]);
                                          onTempChange('kp_id', kp.id);
                                          setShowKPSelector(false);
                                        }}
                                        className={`w-full text-left px-3 py-2.5 text-xs transition-colors flex items-center gap-2 border-b border-amber-50/50 ${kpIdx % 2 === 0 ? 'border-r' : ''} ${currentQ.related_kps?.[0] === kp.name
                                          ? 'bg-amber-50 text-amber-700 font-bold'
                                          : 'bg-white text-neutral-600 hover:bg-amber-50 hover:text-amber-700'
                                          }`}
                                      >
                                        <FaLightbulb className={currentQ.related_kps?.[0] === kp.name ? 'text-amber-500' : 'text-amber-300'} size={12} />
                                        <span className="truncate">{kp.name}</span>
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    currentQ.related_kps?.slice(0, 1).map((kp: string, kidx: number) => (
                      <span
                        key={kidx}
                        onClick={() => {
                          if (onKPLookup && !isEditing) {
                            onKPLookup(kp);
                          }
                        }}
                        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold border bg-amber-50 text-amber-700 border-amber-200 shadow-sm transition-all group/kp max-w-full overflow-hidden ${onKPLookup && !isEditing ? 'cursor-pointer hover:bg-amber-100 hover:scale-[1.02] active:scale-95' : ''}`}
                        title={kp}
                      >
                        <FaLightbulb className="text-amber-500 shrink-0" size={12} />
                        <span className="truncate">{kp}</span>
                        {onKPLookup && !isEditing && (
                          <div className="ml-1 text-amber-400 opacity-60 group-hover/kp:opacity-100 transition-opacity">
                            <FaSearch size={10} />
                          </div>
                        )}
                      </span>
                    ))
                  )}
                </div>
              )}
            </div>

            {/* Toolbar Buttons */}
            {editable && (
              <div className={`shrink-0 flex items-center gap-1.5 transition-opacity duration-200 mt-0.5 ${isEditing ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                {/* Question Bank Star */}
                {onAddToBank && (onRemoveFromBank || onEditBankQuestion) && (
                  <>
                    {question.saved_question_bank_id ? (
                      <div className="p-1.5 text-yellow-400 border border-yellow-100 bg-yellow-50 rounded-lg cursor-help shadow-sm" title="已加入題庫">
                        <FaStar size={12} />
                      </div>
                    ) : (
                      <button
                        onClick={() => onAddToBank(index, question)}
                        className="p-1.5 text-gray-300 hover:text-yellow-400 hover:bg-yellow-50 rounded-lg border border-transparent hover:border-yellow-200 transition-all"
                        title="加入題庫"
                      >
                        <FaRegStar size={12} />
                      </button>
                    )}
                    <div className="w-px h-4 bg-neutral-border mx-1 shadow-[1px_0_0_0_white]"></div>
                  </>
                )}

                {!isEditing ? (
                  <div className="flex items-center gap-0.5 bg-gray-50/50 p-0.5 rounded-lg border border-gray-100">
                    <button
                      onClick={() => onMoveUp && onMoveUp(index)}
                      disabled={isFirstItem}
                      className="p-1.5 text-gray-400 hover:text-theme-primary hover:bg-white hover:shadow-sm rounded-md disabled:opacity-20 transition-all"
                      title="上移"
                    >
                      <FaArrowUp size={12} />
                    </button>
                    <button
                      onClick={() => onMoveDown && onMoveDown(index)}
                      disabled={isLastItem}
                      className="p-1.5 text-gray-400 hover:text-theme-primary hover:bg-white hover:shadow-sm rounded-md disabled:opacity-20 transition-all"
                      title="下移"
                    >
                      <FaArrowDown size={12} />
                    </button>
                    <div className="w-px h-4 bg-gray-200 mx-1"></div>
                    <button
                      onClick={() => {
                        onStartEdit(index, question);
                        if (question.saved_question_bank_id && onEditBankQuestion) {
                          onEditBankQuestion(index, question);
                        }
                      }}
                      className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-white hover:shadow-sm rounded-md transition-all"
                      title={question.saved_question_bank_id ? "編輯內容與題庫資訊" : "編輯內容"}
                    >
                      <FaPen size={12} />
                    </button>
                    <button
                      onClick={() => onDelete && onDelete(index)}
                      className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-white hover:shadow-sm rounded-md transition-all"
                      title="刪除"
                    >
                      <FaTrash size={12} />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => onSaveEdit(index)}
                      className="flex items-center gap-1.5 px-4 py-1.5 bg-theme-primary text-white rounded-lg text-xs font-bold hover:bg-theme-primary-dark transition-all shadow-md active:scale-95"
                    >
                      <FaCheck size={10} /> 儲存
                    </button>
                    <button
                      onClick={onCancelEdit}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-white text-gray-500 border border-gray-200 rounded-lg text-xs font-bold hover:bg-gray-50 transition-all active:scale-95 shadow-sm"
                    >
                      <FaTimes size={10} /> 取消
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
          {isEditing ? (
            <>
              {(type === 'fill_in_blank' || type === 'fill_in_the_blank') && (
                <div className="text-[11px] text-amber-600 font-bold mb-2 flex items-center gap-1.5 bg-amber-50 px-2 py-1 rounded border border-amber-100 w-fit">
                  <FaLightbulb size={12} className="text-amber-500" />
                  <span>操作說明：請直接在題目中使用 ____ (至少四個底線) 來表示填空處</span>
                </div>
              )}
              <textarea
                value={currentQ.question_text}
                onChange={(e) => onTempChange('question_text', e.target.value)}
                className="w-full border border-gray-300 rounded-xl p-3 text-lg font-medium text-neutral-text-main focus:border-theme-primary focus:ring-4 focus:ring-theme-primary/10 outline-none resize-none mb-3 pr-4 transition-all"
                rows={2}
                placeholder="請輸入題目內容..."
              />
            </>
          ) : (
            <div className="font-medium text-neutral-text-main text-lg mb-3 leading-[1.8] whitespace-pre-wrap pr-4 markdown-content">
              {(type === 'fill_in_blank' || type === 'fill_in_the_blank') && currentQ.question_text?.includes('____') ? (
                <div className="flex flex-wrap items-baseline gap-x-0.5">
                  {currentQ.question_text.split(/(____+)/).map((part: string, idx: number) =>
                    part.startsWith('____') ? (
                      <span key={idx} className="inline-flex border-b-2 border-blue-400 min-w-[60px] h-6 bg-blue-50/50 rounded-t sm:mx-1 self-center transition-all hover:bg-blue-100/50" />
                    ) : (
                      <span key={idx} className="inline">
                        <ReactMarkdown components={{ p: 'span', div: 'span' }}>
                          {part}
                        </ReactMarkdown>
                      </span>
                    )
                  )}
                </div>
              ) : (
                <ReactMarkdown components={{ p: ({ node, ...props }) => <p className="mt-0 mb-3 last:mb-0" {...props} /> }}>
                  {currentQ.question_text || currentQ.question || currentQ.title}
                </ReactMarkdown>
              )}
            </div>
          )}


          {/* Options for MCQ / True False */}
          {(type === 'multiple_choice' || type === 'true_false' || (currentQ.options && Object.keys(currentQ.options).length > 0)) && currentQ.options && (
            <div className={`mt-2 ${type === 'true_false' ? 'flex flex-row gap-4' : 'grid grid-cols-1 gap-2'}`}>
              {Object.entries(currentQ.options).map(([key, val]) => {
                const isCorrect = key === currentQ.correct_answer || (key.toLowerCase() === String(currentQ.correct_answer).toLowerCase());

                // True/False Segmented Control Style
                if (type === 'true_false') {
                  const label = key === 'true' ? '是' : '否';
                  return (
                    <div
                      key={key}
                      onClick={() => isEditing && onTempChange('correct_answer', key)}
                      className={`flex items-center justify-center gap-2 px-6 py-1.5 rounded-lg border transition-all text-sm font-bold min-w-[80px] select-none ${isCorrect
                        ? 'bg-green-100 text-green-700 border-green-200 shadow-sm ring-1 ring-green-200'
                        : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300 hover:bg-gray-50'
                        } ${isEditing ? 'cursor-pointer hover:scale-105 active:scale-95' : 'cursor-default'}`}
                    >
                      <span className="text-sm tracking-widest">{label}</span>
                    </div>
                  );
                }

                // Default Multiple Choice Style
                return (
                  <div
                    key={key}
                    className={`flex items-center gap-3 p-2 rounded border transition-all ${isCorrect
                      ? 'bg-green-50 border-green-200'
                      : 'bg-gray-50 border-gray-100 hover:border-gray-200'
                      }`}
                  >
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => isEditing && onTempChange('correct_answer', key)}
                        className={`w-8 h-8 flex items-center justify-center rounded-full text-xs font-bold transition-all ${isCorrect
                          ? 'bg-green-500 text-white shadow-md scale-110'
                          : 'bg-gray-200 text-gray-500 hover:bg-gray-300'
                          } ${isEditing ? 'cursor-pointer' : 'cursor-default'}`}
                      >
                        {key}
                      </button>
                    </div>
                    {/* Only show content for Multiple Choice */}
                    <div className="flex-1">
                      {isEditing ? (
                        <input
                          type="text"
                          value={String(val)}
                          onChange={(e) => onTempOptionChange && onTempOptionChange(key, e.target.value)}
                          className="w-full bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-700 focus:border-theme-primary outline-none transition-all"
                          placeholder={`選項 ${key} 內容...`}
                        />
                      ) : (
                        <div className={`text-sm markdown-content inline-markdown ${isCorrect ? 'text-green-800 font-semibold' : 'text-gray-600'}`}>
                          <ReactMarkdown components={{ p: ({ node, ...props }) => <p className="mt-0 mb-0 px-0" {...props} /> }}>
                            {String(val)}
                          </ReactMarkdown>
                        </div>
                      )}
                    </div>
                    {isCorrect && !isEditing && (
                      <FaCheck className="text-green-500 mr-2" size={12} />
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Sample Answer / Correct Answer for FIB/Short Answer - REDESIGNED */}
          {!['multiple_choice', 'true_false'].includes(type) && (type === 'short_answer' || type === 'fill_in_blank' || type === 'fill_in_the_blank' || isEditing) && (
            <div className={`mt-6 transition-all ${isEditing
              ? 'p-4 rounded-xl border bg-white border-gray-200 shadow-inner'
              : 'pl-4 border-l-4 border-amber-200 bg-amber-50/20 py-1'
              }`}>
              <div className="flex items-center gap-2 mb-2">
                <FaCheckToSlot className="text-amber-400" size={14} />
                <span className="text-[11px] font-bold text-gray-400 uppercase tracking-widest">
                  {(type === 'fill_in_blank' || type === 'fill_in_the_blank') ? '正確填空答案' : '參考解答'}
                </span>
              </div>
              {isEditing ? (
                <textarea
                  value={(type === 'fill_in_blank' || type === 'fill_in_the_blank') ? (currentQ.correct_answer || '') : (currentQ.sample_answer || '')}
                  onChange={(e) => onTempChange((type === 'fill_in_blank' || type === 'fill_in_the_blank') ? 'correct_answer' : 'sample_answer', e.target.value)}
                  className="w-full border border-gray-200 rounded-lg p-3 text-sm text-neutral-text-main focus:border-theme-primary focus:ring-4 focus:ring-theme-primary/5 outline-none resize-none transition-all"
                  rows={(type === 'fill_in_blank' || type === 'fill_in_the_blank') ? 1 : 2}
                  placeholder={(type === 'fill_in_blank' || type === 'fill_in_the_blank') ? "對於填空題，此處為唯一正確評分標準..." : "請輸入參考解答..."}
                />
              ) : (
                <div className="text-base text-neutral-text-main font-medium leading-relaxed markdown-content">
                  <ReactMarkdown components={{ p: ({ node, ...props }) => <p className="mt-0 mb-4 last:mb-0" {...props} /> }}>
                    {(type === 'fill_in_blank' || type === 'fill_in_the_blank') ? (currentQ.correct_answer || '未提供答案') : (currentQ.sample_answer || '無參考解答')}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          )}

          {/* Detailed Explanation - Pedagogical Feedback - ADAPTIVE STYLE */}
          {(currentQ.detailed_explanation || isEditing) && (
            <div className={`mt-6 transition-all overflow-hidden ${isEditing
              ? 'p-4 rounded-xl border bg-white border-blue-200 border-l-4 border-l-blue-500 shadow-inner'
              : 'pl-4 border-l-4 border-blue-200 py-1'
              }`}>
              <div className="flex items-center gap-2 mb-2">
                <RiMarkPenFill className="text-blue-300" size={14} />
                <span className="text-[11px] font-bold text-blue-300 uppercase tracking-widest">
                  深度解析與引導
                </span>
              </div>
              {isEditing ? (
                <textarea
                  value={currentQ.detailed_explanation || ''}
                  onChange={(e) => onTempChange('detailed_explanation', e.target.value)}
                  className="w-full border border-blue-100 rounded-lg p-3 text-sm text-neutral-text-main focus:border-theme-primary focus:ring-4 focus:ring-theme-primary/5 outline-none resize-none bg-white transition-all"
                  rows={3}
                  placeholder="請輸入引導式解析，包含邏輯說明與引導建議..."
                />
              ) : (
                <div className="text-sm text-blue-900/80 font-medium leading-relaxed markdown-content">
                  <ReactMarkdown components={{ p: ({ node, ...props }) => <p className="mt-0 mb-4 last:mb-0" {...props} /> }}>
                    {currentQ.detailed_explanation || '尚未提供詳細解析。'}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          )}

          {/* Bottom Footer: KPs & References */}
          <div className="mt-4 flex flex-wrap justify-between items-end gap-3 min-h-[32px]">

            {/* Right: Source Reference */}
            {currentQ.source?.chunk_ids && currentQ.source.chunk_ids.length > 0 && !isEditing && (
              <div className="flex-shrink-0 ml-auto">
                <button
                  onClick={() => {
                    if (onReferenceClick && currentQ.source?.chunk_ids) {
                      const fullChunk = {
                        chunk_id: currentQ.source.chunk_ids[0],
                        text: currentQ.source.text || '',
                        source_metadata: currentQ.source.source_metadata || {}
                      };
                      onReferenceClick(
                        currentQ.source.chunk_ids[0],
                        "語義匹配 (Semantic Match)",
                        currentQ.source.match_score,
                        fullChunk,
                        // Prefer explicit DB id, fall back to display number (always available)
                        currentQ.id || currentQ.question_number || displayNumber || undefined,
                        'question'
                      );
                    }
                  }}
                  className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-colors border bg-blue-50 text-blue-600 border-blue-100 hover:bg-blue-100"
                  title={`來源: ${currentQ.source.source_metadata?.document_name || currentQ.source.filename || currentQ.source.source || '未知'} (Page ${currentQ.source.page_number})`}
                >
                  <FaLink size={10} />
                  <span className="max-w-[150px] truncate">
                    {currentQ.source.source_metadata?.document_name || currentQ.source.filename || currentQ.source.source || '參考來源'}
                  </span>
                  {currentQ.source.page_number && (
                    <span className="font-mono text-[10px] opacity-80">
                      {!String(currentQ.source.page_number).startsWith('P.') ? `(P.${currentQ.source.page_number})` : `(${currentQ.source.page_number})`}
                    </span>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div >
  );
};
