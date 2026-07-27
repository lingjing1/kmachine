import { useEffect } from 'react';
import ReactDOM from 'react-dom';
import { FaTimes, FaCheckCircle } from 'react-icons/fa';
import MaterialSelectionView, { MaterialSelectionViewProps } from './MaterialSelectionView';

export interface MaterialSelectionModalProps extends Omit<MaterialSelectionViewProps, 'footerActions'> {
    isOpen: boolean;
    onClose: () => void;
    title?: string;
    confirmText?: string;
    onConfirm?: () => void;
    isConfirmLoading?: boolean;
}

export default function MaterialSelectionModal({
    isOpen,
    onClose,
    title = '選擇參考資料',
    confirmText = '完成選擇',
    onConfirm,
    isConfirmLoading = false,
    ...viewProps
}: MaterialSelectionModalProps) {
    const selectedCount = viewProps.selectedKeys.size;

    useEffect(() => {
        if (isOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = 'unset';
        }
        return () => {
            document.body.style.overflow = 'unset';
        };
    }, [isOpen]);

    if (!isOpen) return null;

    return ReactDOM.createPortal(
        <div className="fixed inset-0 bg-black bg-opacity-50 z-[9999] flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-6xl h-[90vh] sm:h-[85vh] overflow-hidden flex flex-col transform transition-all border border-gray-100">
                {/* Gradient Header */}
                <div className="flex-none flex items-center justify-between px-6 py-4 bg-gradient-to-r from-blue-50 via-cyan-50 to-blue-50 border-b border-blue-100 shrink-0 shadow-sm relative z-10">
                    <h3 className="text-lg font-bold bg-gradient-to-r from-blue-700 to-cyan-600 bg-clip-text text-transparent tracking-wide">
                        {title}
                    </h3>
                    <div className="flex gap-2 items-center">
                        {viewProps.activeTab === 'uploaded' && selectedCount > 0 && (
                            <span className="text-sm font-medium text-blue-700 mr-2 bg-blue-100/50 px-3 py-1 rounded-full border border-blue-200">
                                已選擇 {selectedCount} 個
                            </span>
                        )}
                        <button
                            onClick={onClose}
                            className="p-2 rounded-full text-neutral-icon hover:bg-white/80 hover:text-blue-600 transition-all duration-200 hover:shadow-md"
                            aria-label="關閉"
                        >
                            <FaTimes className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Body using reusable component */}
                <div className="flex-1 overflow-hidden bg-white">
                    <MaterialSelectionView
                        {...viewProps}
                        footerActions={
                            <div className="flex justify-end gap-3">
                                <button
                                    onClick={onClose}
                                    className="px-5 py-2.5 text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-xl text-sm font-semibold transition-all"
                                >
                                    取消
                                </button>
                                <button
                                    onClick={() => {
                                        if (onConfirm) onConfirm();
                                        else onClose();
                                    }}
                                    disabled={isConfirmLoading || (selectedCount === 0 && onConfirm !== undefined)}
                                    className="px-6 py-2.5 bg-theme-primary text-white rounded-xl hover:bg-blue-700 hover:shadow-lg disabled:opacity-50 text-sm font-bold shadow-md shadow-blue-500/20 transition-all flex items-center gap-2"
                                >
                                    <FaCheckCircle className="w-4 h-4" />
                                    {confirmText} {selectedCount > 0 ? `(${selectedCount})` : ''}
                                </button>
                            </div>
                        }
                    />
                </div>
            </div>
        </div>,
        document.body
    );
}
