import React, { useEffect, useState } from 'react';
import { FaTimes, FaSpinner, FaLightbulb } from 'react-icons/fa';
import { getLimeReport, LimeReportResponse, FeatureWeight, TextHighlight } from '../../services/studentApi';

interface LimeReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  kpId: number;
  studentId?: number; // Optional: student_id can be inferred from JWT
  unitName: string;
  kpName: string;
  stage?: 'preview' | 'review'; // Add stage prop
}

const LimeReportModal: React.FC<LimeReportModalProps> = ({
  isOpen, onClose, kpId, studentId, unitName, kpName, stage = 'preview'
}) => {
  const [report, setReport] = useState<LimeReportResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch report data when modal opens
  useEffect(() => {
    if (isOpen && kpId) {
      setLoading(true);
      setError(null);
      setReport(null);
      
      const fetchReport = async () => {
        try {
          // Use the stage prop passed from parent
          const data = await getLimeReport(kpId, { 
            stage, 
            teacherOverrideStudentId: studentId 
          });
          setReport(data);
        } catch (err: any) {
          console.error(err);
          setError("尚無此階段的學習資料");
        } finally {
          setLoading(false);
        }
      };

      fetchReport();
    }
  }, [isOpen, kpId, studentId, stage]);

  if (!isOpen) return null;

  // --- Helper Components ---

  // Performance labels injected by LIME — should NOT be highlighted in the answer text
  const PERFORMANCE_LABELS = new Set(['correct', 'partially_correct', 'incorrect']);

  const FormattedAnswerDisplay = ({ original, highlights, featureWeights }: { original: string, highlights: TextHighlight[], featureWeights: FeatureWeight[] }) => {
    // Parse the text into structured Q&A sections
    const sections: Array<{ question: string; reference: string; answer: string; performance: string; startIdx: number; endIdx: number }> = [];
    
    // Split into Q&A groups by ［題目］ marker.
    // IMPORTANT: Do NOT split by empty lines — student answers can contain blank lines within them.
    const qaGroups = original.split(/(?=［題目］)/);
    let currentIndex = 0;

    // Extract a section's full content including embedded blank lines.
    // Matches from the tag colon up to the next ［...］ tag or end of string.
    const extractSectionFromGroup = (group: string, tag: string): string | undefined => {
      const regex = new RegExp(`${tag}[:：]\\s*([\\s\\S]*?)(?=\\s*［[^］]+］|\\s*$)`);
      const match = group.match(regex);
      return match ? match[1].trim() : undefined;
    };

    qaGroups.forEach(group => {
      if (!group.trim()) return;
      const question = extractSectionFromGroup(group, '［題目］');
      const reference = extractSectionFromGroup(group, '［參考答案］');
      const answer = extractSectionFromGroup(group, '［學生答案］');
      const performance = extractSectionFromGroup(group, '［學生表現］');

      if (question && answer) {
        // Find answer position in original text
        const answerStart = original.indexOf(answer, currentIndex);
        const answerEnd = answerStart + answer.length;

        sections.push({ question: question!, reference: reference ?? '', answer: answer!, performance: performance ?? '', startIdx: answerStart, endIdx: answerEnd });
        currentIndex = answerEnd;
      }
    });
    
    // Helper to render highlighted answer text.
    // Priority: use server-computed highlight positions; fall back to searching featureWeights keywords directly.
    const renderHighlightedAnswer = (answer: string, startIdx: number, endIdx: number) => {
      const serverHighlights = highlights.filter(h => h.start >= startIdx && h.end <= endIdx && h.weight > 0);

      // --- Build highlight spans from server positions or keyword fallback ---
      let spansToRender: Array<{ start: number; end: number; weight: number; label: string }> = [];

      if (serverHighlights.length > 0) {
        // Use server-provided positions (relative to `original`)
        spansToRender = serverHighlights.map(h => ({
          start: h.start,
          end: h.end,
          weight: h.weight,
          label: original.substring(h.start, h.end)
        }));
      } else {
        // Fallback: search positive-weight keywords (excluding performance labels) in answer text
        const positiveKws = featureWeights
          .filter(fw => fw.weight > 0 && !PERFORMANCE_LABELS.has(fw.keyword.toLowerCase()))
          .sort((a, b) => b.keyword.length - a.keyword.length); // longer first to avoid partial overlaps

        const occupied: boolean[] = new Array(answer.length).fill(false);
        for (const fw of positiveKws) {
          const re = new RegExp(fw.keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
          let m: RegExpExecArray | null;
          while ((m = re.exec(answer)) !== null) {
            if (!occupied.slice(m.index, m.index + m[0].length).some(Boolean)) {
              for (let i = m.index; i < m.index + m[0].length; i++) occupied[i] = true;
              // Convert answer-relative position to original-relative
              spansToRender.push({
                start: startIdx + m.index,
                end: startIdx + m.index + m[0].length,
                weight: fw.weight,
                label: m[0]
              });
            }
          }
        }
        spansToRender.sort((a, b) => a.start - b.start);
      }

      if (spansToRender.length === 0) {
        return <span className="text-gray-800 whitespace-pre-wrap">{answer}</span>;
      }

      let lastIndex = startIdx;
      const elements: React.ReactNode[] = [];
      spansToRender.forEach((h, idx) => {
        if (h.start > lastIndex) {
          elements.push(<span key={`text-${idx}`}>{original.substring(lastIndex, h.start)}</span>);
        }
        elements.push(
          <span
            key={`high-${idx}`}
            className="bg-green-200 px-0.5 rounded cursor-help"
            title={`正向關鍵詞，影響權重: +${h.weight.toFixed(4)}`}
          >
            {original.substring(h.start, h.end)}
          </span>
        );
        lastIndex = h.end;
      });
      if (lastIndex < endIdx) {
        elements.push(<span key="text-end">{original.substring(lastIndex, endIdx)}</span>);
      }
      return <div className="text-gray-800 whitespace-pre-wrap">{elements}</div>;
    };
    
    return (
      <div className="space-y-4">
        {sections.map((section, idx) => (
          <div key={idx} className="border border-gray-200 rounded-lg p-4 bg-white shadow-sm">
            <div className="mb-3">
              <div className="text-xs font-semibold text-blue-600 mb-1">題目 {idx + 1}</div>
              <div className="text-gray-700 text-sm">{section.question}</div>
            </div>
            
            {section.reference && (
              <div className="mb-3 pb-3 border-b border-gray-100">
                <div className="text-xs font-semibold text-gray-500 mb-1">參考答案</div>
                <div className="text-gray-600 text-sm">{section.reference}</div>
              </div>
            )}
            
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-semibold text-green-600">學生答案</span>
                {section.performance && (
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    section.performance === 'Correct' ? 'bg-green-100 text-green-700' :
                    section.performance === 'Partially Correct' ? 'bg-yellow-100 text-yellow-700' :
                    section.performance === 'Incorrect' ? 'bg-red-100 text-red-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {section.performance === 'Correct' ? '✓ 正確' :
                     section.performance === 'Partially Correct' ? '△ 部分正確' :
                     section.performance === 'Incorrect' ? '✗ 不正確' :
                     section.performance}
                  </span>
                )}
              </div>
              <div className="text-sm leading-relaxed">
                {renderHighlightedAnswer(section.answer, section.startIdx, section.endIdx)}
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  };

  const FeatureWeightChart = ({ weights }: { weights: FeatureWeight[] }) => {
    // Defensive check: ensure weights is an array
    const safeWeights = Array.isArray(weights) ? weights : [];
    
    // Filter only positive weights (we only show positive keywords now)
    const positive = safeWeights.filter(w => w.weight > 0).sort((a, b) => b.weight - a.weight);

    const BarItem = ({ w, isPositive }: { w: FeatureWeight, isPositive: boolean }) => (
      <div className="flex items-center gap-2 mb-2 text-sm">
        <span className="w-24 truncate text-right font-medium text-gray-600" title={w.keyword}>
          {w.keyword}
        </span>
        <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden flex">
          {/* Bar width calculation could be normalized, here simplified */}
          <div 
            className={`h-full ${isPositive ? 'bg-green-500' : 'bg-red-500'}`} 
            style={{ width: `${Math.min(Math.abs(w.weight) * 300, 100)}%` }} // Scaling factor
          ></div>
        </div>
        <span className={`w-12 text-xs font-mono ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
          {w.weight > 0 ? '+' : ''}{w.weight.toFixed(3)}
        </span>
      </div>
    );

    return (
      <div className="space-y-4">
        {positive.length > 0 && (
          <div>
            <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">正向關鍵詞</h4>
            {positive.map((w, i) => <BarItem key={i} w={w} isPositive={true} />)}
          </div>
        )}
        {positive.length === 0 && (
          <div className="text-center py-8 text-gray-400">
            <p className="text-sm mb-1">無正向關鍵詞</p>
            <p className="text-xs">學生回答中未找到支持當前掌握度預測的關鍵詞彙</p>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gray-50">
          <div>
            <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
              <FaLightbulb className="text-yellow-500" />
              AI 學習診斷報告
            </h2>
            <p className="text-sm text-gray-500 mt-1">
              單元：{unitName} / 知識點：{kpName}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-2 rounded-full hover:bg-gray-200 transition">
            <FaTimes size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-white">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-64 space-y-4">
              <FaSpinner className="animate-spin text-4xl text-blue-500" />
              <p className="text-gray-500">正在分析您的學習歷程...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-64 text-slate-500 bg-slate-50 rounded-lg border border-slate-200">
              <p className="text-lg font-medium">{error}</p>
              <p className="text-sm mt-2 text-slate-400">請先完成此階段的學習內容</p>
            </div>
          ) : report ? (
            <div className="flex flex-col lg:flex-row gap-8 h-full">
              
              {/* Left Column: Highlighted Text */}
              <div className="flex-1 min-w-0 flex flex-col">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="font-bold text-gray-700 flex items-center gap-2">
                    <span className="w-1.5 h-6 bg-blue-500 rounded-full"></span>
                    作答內容分析
                  </h3>
                  <div className="flex gap-3 text-xs">
                    <span className="flex items-center gap-1"><span className="w-3 h-3 bg-green-200 rounded"></span> 正向關鍵字</span>
                    <span className="flex items-center gap-1"><span className="w-3 h-3 bg-red-200 rounded"></span> 負向關鍵字</span>
                  </div>
                </div>
                
                <div className="bg-gray-50 rounded-lg p-5 border border-gray-200 shadow-inner flex-1 overflow-y-auto">
                  {report.highlighted_text ? (
                    <FormattedAnswerDisplay 
                      original={report.highlighted_text.original} 
                      highlights={report.highlighted_text.highlights}
                      featureWeights={report.feature_weights}
                    />
                  ) : (
                    <p className="text-gray-400 italic">無文本資料</p>
                  )}
                </div>
              </div>

              {/* Right Column: Feature Weights */}
              <div className="w-full lg:w-1/3 min-w-[300px] flex flex-col border-l border-gray-100 pl-8">
                <h3 className="font-bold text-gray-700 mb-4 flex items-center gap-2">
                   <span className="w-1.5 h-6 bg-purple-500 rounded-full"></span>
                   關鍵特徵權重
                </h3>
                <div className="bg-white rounded-lg flex-1 overflow-y-auto pr-2">
                  <FeatureWeightChart weights={report.feature_weights} />
                </div>
                
                {/* Interpretation Hint */}
                <div className="mt-6 bg-blue-50 p-4 rounded-lg text-sm text-blue-800 border border-blue-100">
                  <p className="font-bold mb-1">💡 如何解讀？</p>
                  <p>綠色代表這個詞「支持」目前的評級（如精熟）。</p>
                </div>
              </div>

            </div>
          ) : (
            <div className="text-center text-gray-400 mt-20">無報告資料</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LimeReportModal;
