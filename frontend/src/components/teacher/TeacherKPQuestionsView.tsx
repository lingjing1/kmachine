import React, { useState, useEffect } from 'react';
import { FaSpinner, FaExclamationCircle, FaSearch } from 'react-icons/fa';
import API_BASE_URL from '../../config/api';
import { ExamContentView } from '../reports/ExamContentView';

interface TeacherKPQuestionsViewProps {
    courseId: string | number;
    kpId: number;
    kpName: string;
    onCountUpdate?: (count: number) => void;
}

const TeacherKPQuestionsView: React.FC<TeacherKPQuestionsViewProps> = ({
    courseId,
    kpId,
    kpName,
    onCountUpdate
}) => {
    const [questions, setQuestions] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchKPQuestions = async () => {
            if (!courseId || !kpId) return;

            try {
                setIsLoading(true);
                setError(null);

                // Fetch questions specifically for this KP from the question bank
                // Using per_page=100 to show "all" as requested
                const response = await fetch(
                    `${API_BASE_URL}/api/courses/${courseId}/question-bank?kp_id=${kpId}&per_page=1000`
                );

                if (!response.ok) {
                    throw new Error('無法載入題庫題目');
                }

                const data = await response.json();

                // Update parent with count
                if (onCountUpdate) {
                    onCountUpdate(data.length);
                }

                // Transform data for ExamContentView if necessary
                const transformed = data.map((item: any) => ({
                    ...item.question_data,
                    id: item.id,
                    question_type: item.question_type,
                    title: item.title,
                    tags: item.tags, // Include tags
                    saved_question_bank_id: item.id, // Mark as already in bank
                    related_kps: [item.kp_name || kpName]
                }));

                setQuestions(transformed);
            } catch (err: any) {
                console.error('Failed to fetch KP questions:', err);
                setError(err.message || '載入失敗');
            } finally {
                setIsLoading(false);
            }
        };

        fetchKPQuestions();
    }, [courseId, kpId, kpName]);

    if (isLoading) {
        return (
            <div className="py-12 flex flex-col items-center justify-center gap-4">
                <FaSpinner className="animate-spin text-theme-primary" size={32} />
                <span className="text-gray-500 font-medium">正在從題庫索取「{kpName}」的題目...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="py-12 text-center">
                <FaExclamationCircle className="mx-auto mb-4 text-red-400" size={48} />
                <h3 className="text-lg font-bold text-gray-800 mb-2">出錯了</h3>
                <p className="text-gray-500">{error}</p>
            </div>
        );
    }

    if (questions.length === 0) {
        return (
            <div className="py-24 text-center">
                <FaSearch className="mx-auto mb-4 text-gray-300" size={48} />
                <h3 className="text-lg font-bold text-gray-800 mb-2">題庫中尚無對應題目</h3>
                <p className="text-gray-500">目前針對「{kpName}」還沒有任何已發布的試題。</p>
            </div>
        );
    }

    return (
        <div className="space-y-8 pb-12">
            {questions.map((q, idx) => (
                <ExamContentView
                    key={q.id || idx}
                    question={q}
                    index={idx}
                    displayNumber={idx + 1}
                    editable={false} // Teacher lookup mode is read-only for now
                    isEditing={false}
                    onStartEdit={() => { }}
                    onSaveEdit={() => { }}
                    onCancelEdit={() => { }}
                    onTempChange={() => { }}
                />
            ))}
        </div>
    );
};

export default TeacherKPQuestionsView;
