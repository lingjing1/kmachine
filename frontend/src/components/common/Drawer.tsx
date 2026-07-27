import React, { useEffect } from 'react';
import ReactDOM from 'react-dom';
import { FaTimes } from 'react-icons/fa';

interface DrawerProps {
    isOpen: boolean;
    onClose: () => void;
    children: React.ReactNode;
    title?: string;
    width?: string | number; // e.g., 'max-w-md' or pixel number
}

const Drawer: React.FC<DrawerProps> = ({
    isOpen,
    onClose,
    children,
    title,
    width = 'max-w-lg'
}) => {
    // Prevent body scroll when drawer is open
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
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-transparent z-40 transition-opacity duration-300"
                onClick={onClose}
                aria-hidden="true"
            />

            {/* Drawer Panel */}
            <div
                className={`fixed inset-y-0 right-0 z-50 bg-white shadow-2xl transform transition-transform duration-300 ease-in-out flex flex-col ${typeof width === 'string' ? width : ''}`}
                style={typeof width === 'number' ? { width: `${width}px` } : {}}
                role="dialog"
                aria-modal="true"
            >
                {/* Header */}
                <div className="flex-none flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/60">
                    <h3 className="text-xl font-bold text-gray-900">{title || 'Details'}</h3>
                    <button
                        onClick={onClose}
                        className="p-2 -mr-2 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                        aria-label="Close panel"
                    >
                        <FaTimes className="w-5 h-5" />
                    </button>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto p-6 scroll-smooth">
                    {children}
                </div>
            </div>
        </>,
        document.body
    );
};

export default Drawer;
