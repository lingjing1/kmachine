import { useEffect } from 'react';
import ReactDOM from 'react-dom';
import { FaCheckCircle, FaTimes, FaExclamationCircle, FaInfoCircle } from 'react-icons/fa';

interface ToastProps {
    message: string;
    type?: 'success' | 'error' | 'info';
    duration?: number;
    onClose: () => void;
    position?: 'top-center' | 'top-right' | 'top-left';
}

function Toast({ message, type = 'success', duration = 3000, onClose, position = 'top-right' }: ToastProps) {
    useEffect(() => {
        const timer = setTimeout(() => {
            onClose();
        }, duration);

        return () => clearTimeout(timer);
    }, [duration, onClose]);

    const bgColors = {
        success: 'bg-green-50 border-green-500',
        error: 'bg-red-50 border-red-500',
        info: 'bg-blue-50 border-blue-500'
    };

    const textColors = {
        success: 'text-green-800',
        error: 'text-red-800',
        info: 'text-blue-800'
    };

    const iconColors = {
        success: 'text-green-600',
        error: 'text-red-600',
        info: 'text-blue-600'
    };

    const positionClasses = {
        'top-center': 'top-10 left-1/2 -translate-x-1/2 animate-slide-in-top',
        'top-right': 'top-6 right-0 animate-slide-in-right',
        'top-left': 'top-6 left-6 animate-slide-in-left'
    };

    const Icon = type === 'error' ? FaExclamationCircle : type === 'info' ? FaInfoCircle : FaCheckCircle;

    return ReactDOM.createPortal(
        <div
            className={`fixed z-[99999] ${positionClasses[position]} pointer-events-none`}
            style={{ isolation: 'isolate' }}
        >
            <div className={`
                ${bgColors[type]} ${textColors[type]}
                px-6 py-4 shadow-lg border-l-4
                ${position === 'top-right' ? 'rounded-l-lg rounded-r-none' : 'rounded-lg'}
                flex items-start gap-3 min-w-[320px] max-w-2xl
                transform transition-all duration-300 pointer-events-auto
            `}>
                <Icon className={`${iconColors[type]} flex-shrink-0 mt-0.5`} size={20} />
                <div className="flex-1 overflow-hidden">
                    <p className="font-medium break-words whitespace-pre-wrap leading-relaxed">
                        {message}
                    </p>
                </div>
                <button
                    onClick={onClose}
                    className={`${iconColors[type]} hover:opacity-70 transition-opacity`}
                >
                    <FaTimes size={16} />
                </button>
            </div>
        </div>,
        document.body
    );
}

export default Toast;
