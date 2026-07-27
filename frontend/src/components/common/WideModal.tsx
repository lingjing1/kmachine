// frontend/src/components/common/WideModal.tsx
import React from 'react';
import ReactDOM from 'react-dom';
import { FaTimes } from 'react-icons/fa';

interface WideModalProps {
    isOpen: boolean;
    onClose: () => void;
    children: React.ReactNode;
    title?: string;
}

const WideModal: React.FC<WideModalProps> = ({ isOpen, onClose, children, title }) => {
    if (!isOpen) return null;

    return ReactDOM.createPortal(
        <>
            {/* Overlay with subtle gradient */}
            <div
                className="fixed inset-0 bg-gradient-to-br from-black/50 via-black/40 to-black/50 z-40 transition-opacity backdrop-blur-sm"
                onClick={onClose}
            ></div>

            {/* Modal Content - Extra Wide with refined styling */}
            <div
                className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-2xl shadow-2xl z-50 w-full max-w-5xl mx-auto max-h-[90vh] overflow-hidden border border-neutral-border/20"
            >
                {/* Header with subtle gradient */}
                <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-blue-50 via-cyan-50 to-blue-50 border-b border-blue-100">
                    <h3 className="text-lg font-bold bg-gradient-to-r from-blue-700 to-cyan-600 bg-clip-text text-transparent">
                        {title || ''}
                    </h3>
                    <button
                        onClick={onClose}
                        className="p-2 rounded-full text-neutral-icon hover:bg-white/80 hover:text-blue-600 transition-all duration-200 hover:shadow-md"
                        aria-label="關閉"
                    >
                        <FaTimes className="w-4 h-4" />
                    </button>
                </div>

                {/* Body with scroll - Removed pt-6 to allow sticky elements to sit flush against header */}
                <div className="px-6 pb-6 overflow-y-auto max-h-[calc(90vh-64px)]">
                    {children}
                </div>
            </div>
        </>,
        document.body
    );
};

export default WideModal;
