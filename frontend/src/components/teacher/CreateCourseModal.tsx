import { useState } from 'react';
import WideModal from '../common/WideModal';
import RichTextEditor from '../common/RichTextEditor';
import Button from '../common/Button';
import { useUser } from '../../contexts/UserContext';
import API_BASE_URL from '../../config/api';

interface CreateCourseModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSuccess: (courseId: number) => void;
}

function CreateCourseModal({ isOpen, onClose, onSuccess }: CreateCourseModalProps) {
    const { user } = useUser();
    const [formData, setFormData] = useState({
        name: '',
        semester: '113-2', // Default to next semester
        description: ''
    });
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async () => {
        if (!formData.name.trim()) {
            setError('請輸入課程名稱');
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            const response = await fetch(`${API_BASE_URL}/api/courses`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: formData.name,
                    semester_name: formData.semester,
                    description: formData.description,
                    teacher_id: user?.user_id
                })
            });

            if (response.ok) {
                const newCourse = await response.json();

                // Call onSuccess callback with new course ID
                onSuccess(newCourse.id);

                // Close modal and reset form
                onClose();
                setFormData({ name: '', semester: '113-2', description: '' });
                setError(null);
            } else {
                setError('建立課程失敗，請稍後再試');
            }
        } catch (err) {
            console.error('Failed to create course:', err);
            setError('目前無法連線到伺服器');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <WideModal
            isOpen={isOpen}
            onClose={onClose}
            title="建立新課程"
        >
            <div className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-neutral-text-main mb-1">
                        課程名稱 <span className="text-destructive">*</span>
                    </label>
                    <input
                        type="text"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        className="w-full px-4 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-theme-ring focus:border-theme-primary"
                        placeholder="例如：人工智慧導論"
                    />
                </div>

                <div className="grid grid-cols-1 gap-4">
                    <div>
                        <label className="block text-sm font-medium text-neutral-text-main mb-1">
                            學期
                        </label>
                        <input
                            type="text"
                            value={formData.semester}
                            onChange={(e) => setFormData({ ...formData, semester: e.target.value })}
                            className="w-full px-4 py-2 border border-neutral-border rounded-lg focus:ring-2 focus:ring-theme-ring focus:border-theme-primary"
                            placeholder="例如：113-2"
                        />
                    </div>
                </div>

                <div>
                    <label className="block text-sm font-medium text-neutral-text-main mb-1">
                        課程說明
                    </label>
                    <RichTextEditor
                        value={formData.description}
                        onChange={(value) => setFormData({ ...formData, description: value })}
                        placeholder="請輸入課程簡介..."
                    />
                </div>

                {error && (
                    <p className="text-sm text-destructive">{error}</p>
                )}

                <div className="flex justify-end gap-3 pt-2">
                    <Button
                        variant="secondary"
                        onClick={onClose}
                        idleText="取消"
                    />
                    <Button
                        variant="primary"
                        onClick={handleSubmit}
                        idleText="建立課程"
                        loadingText="建立中..."
                        buttonState={isLoading ? 'loading' : 'idle'}
                        disabled={!formData.name.trim()}
                    />
                </div>
            </div>
        </WideModal>
    );
}

export default CreateCourseModal;
