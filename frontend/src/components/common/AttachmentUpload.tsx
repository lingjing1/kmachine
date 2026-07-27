import React, { useRef, useState } from 'react';
import { FaUpload, FaTimes, FaCloudUploadAlt } from 'react-icons/fa';

interface AttachmentUploadProps {
    onUpload: (file: File) => Promise<void>;
    maxSizeMB?: number;
    allowedExtensions?: string[];
    className?: string;
}

const AttachmentUpload: React.FC<AttachmentUploadProps> = ({
    onUpload,
    maxSizeMB = 50,
    allowedExtensions = ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.zip', '.rar', '.7z', '.jpg', '.jpeg', '.png', '.gif', '.txt'],
    className = ''
}) => {
    const [isDragging, setIsDragging] = useState(false);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string>('');
    const fileInputRef = useRef<HTMLInputElement>(null);

    const validateFile = (file: File): string | null => {
        // 檢查檔案大小
        const maxBytes = maxSizeMB * 1024 * 1024;
        if (file.size > maxBytes) {
            return `檔案過大，最大允許 ${maxSizeMB}MB`;
        }

        // 檢查檔案是否為空
        if (file.size === 0) {
            return '您選擇的檔案內容為空，請確認您選擇的檔案。';
        }

        // 檢查副檔名
        const extension = '.' + file.name.split('.').pop()?.toLowerCase();
        if (!allowedExtensions.includes(extension)) {
            return `不支援的檔案類型，允許：${allowedExtensions.join(', ')}`;
        }

        return null;
    };

    const handleFileSelect = (file: File) => {
        const validationError = validateFile(file);
        if (validationError) {
            setError(validationError);
            setSelectedFile(null);
            return;
        }

        setError('');
        setSelectedFile(file);
    };

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = () => {
        setIsDragging(false);
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileSelect(files[0]);
        }
    };

    const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (files && files.length > 0) {
            handleFileSelect(files[0]);
        }
    };

    const handleUpload = async () => {
        if (!selectedFile) return;

        setIsUploading(true);
        setError('');

        try {
            await onUpload(selectedFile);
            setSelectedFile(null);
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
        } catch (err: any) {
            setError(err.message || '上傳失敗');
        } finally {
            setIsUploading(false);
        }
    };

    const handleClearSelection = () => {
        setSelectedFile(null);
        setError('');
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    return (
        <div className={className}>
            {/* 拖放區域 */}
            <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => !selectedFile && fileInputRef.current?.click()}
                className={`
                    border-2 border-dashed rounded-xl p-4 text-center transition-all cursor-pointer group flex flex-col items-center justify-center min-h-[120px]
                    ${isDragging ? 'border-theme-primary bg-blue-50' : selectedFile ? 'border-green-500 bg-green-50' : 'border-gray-300 hover:border-theme-primary hover:bg-theme-primary-light/10'}
                `}
            >
                {!selectedFile ? (
                    <>
                        <div className="w-8 h-8 bg-gray-100 rounded-full flex items-center justify-center mb-2 group-hover:bg-theme-primary/10 transition-colors">
                            <FaCloudUploadAlt className={`w-4 h-4 ${isDragging ? 'text-theme-primary' : 'text-gray-400 group-hover:text-theme-primary'}`} />
                        </div>
                        <p className="text-sm font-medium text-gray-700 group-hover:text-theme-primary transition-colors">
                            點擊選擇檔案或拖曳檔案至此處以上傳
                        </p>
                        <p className="text-[10px] text-gray-400 mt-1 leading-tight">
                            支援檔案格式: {allowedExtensions.join(', ')} · 最大 {maxSizeMB}MB
                        </p>
                    </>
                ) : (
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <FaUpload className="text-green-600" size={24} />
                            <div className="text-left">
                                <p className="text-sm font-medium text-neutral-text-main">
                                    {selectedFile.name}
                                </p>
                                <p className="text-xs text-neutral-text-secondary">
                                    {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                                </p>
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={handleClearSelection}
                            className="p-2 rounded-lg text-neutral-icon hover:text-destructive hover:bg-red-50 transition-all"
                            title="取消選擇"
                        >
                            <FaTimes size={16} />
                        </button>
                    </div>
                )}

                <input
                    ref={fileInputRef}
                    type="file"
                    onChange={handleFileInputChange}
                    accept={allowedExtensions.join(',')}
                    className="hidden"
                />
            </div>

            {/* 錯誤訊息 */}
            {error && (
                <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                    {error}
                </div>
            )}

            {/* 上傳按鈕 */}
            {selectedFile && !error && (
                <div className="mt-4 flex justify-end">
                    <button
                        type="button"
                        onClick={handleUpload}
                        disabled={isUploading}
                        className="btn-primary text-sm"
                    >
                        {isUploading ? '上傳中...' : '上傳附件'}
                    </button>
                </div>
            )}
        </div>
    );
};

export default AttachmentUpload;
