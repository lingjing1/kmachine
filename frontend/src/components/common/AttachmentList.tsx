// AttachmentList Component: 顯示附件列表，支援下載與刪除
import API_BASE_URL from '../../config/api';
import { FaDownload, FaTrash } from 'react-icons/fa';
import { getFileIcon } from '../../utils/contentUtils';
import { formatDateTime } from '../../utils/dateUtils';

export interface Attachment {
    id: number;
    file_name: string;
    original_file_name: string;
    file_size_bytes: number;
    file_type: string;
    uploaded_at: string;
    uploaded_by_name: string;
    download_url: string;
}

interface AttachmentListProps {
    attachments: Attachment[];
    onDelete?: (attachmentId: number) => void;
    canDelete?: boolean;
    showUploader?: boolean;
    className?: string;
}

const AttachmentList: React.FC<AttachmentListProps> = ({
    attachments,
    onDelete,
    canDelete = false,
    showUploader = true,
    className = ''
}) => {


    const formatFileSize = (bytes: number): string => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const formatDate = (dateString: string): string => {
        return formatDateTime(dateString);
    };

    const handleDownload = (attachment: Attachment) => {
        // 使用 anchor 標籤觸發下載
        const link = document.createElement('a');
        link.href = `${API_BASE_URL}${attachment.download_url}`;
        link.download = attachment.original_file_name;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    if (attachments.length === 0) {
        return null;
    }

    return (
        <div className={`space-y-2 ${className}`}>
            {attachments.map((attachment) => (
                <div
                    key={attachment.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-neutral-border hover:bg-gray-100 transition-colors"
                >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                        {getFileIcon(attachment.file_type, attachment.file_name, 20, "flex items-center justify-center")}
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-neutral-text-main truncate">
                                {attachment.original_file_name}
                            </p>
                            <p className="text-xs text-neutral-text-secondary">
                                {formatFileSize(attachment.file_size_bytes)}
                                {showUploader && ` · ${attachment.uploaded_by_name}`}
                                {` · ${formatDate(attachment.uploaded_at)}`}
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center gap-1 flex-shrink-0">
                        <button
                            onClick={() => handleDownload(attachment)}
                            className="p-2 rounded-lg text-neutral-icon hover:text-theme-primary hover:bg-theme-primary-light/20 transition-all"
                            title="下載附件"
                        >
                            <FaDownload size={14} />
                        </button>

                        {canDelete && onDelete && (
                            <button
                                onClick={() => onDelete(attachment.id)}
                                className="p-2 rounded-lg text-neutral-icon hover:text-destructive hover:bg-red-50 transition-all"
                                title="刪除附件"
                            >
                                <FaTrash size={14} />
                            </button>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
};

export default AttachmentList;
