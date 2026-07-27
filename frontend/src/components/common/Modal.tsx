// frontend/src/components/common/Modal.tsx
import React from 'react';
import ReactDOM from 'react-dom';
import { FaTimes } from 'react-icons/fa';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  title?: string;
  maxWidth?: string;
  bodyClassName?: string;
  hideHeader?: boolean;
}

const Modal: React.FC<ModalProps> = ({ isOpen, onClose, children, title, maxWidth = 'max-w-lg', bodyClassName = 'p-6', hideHeader = false }) => {
  if (!isOpen) return null;

  return ReactDOM.createPortal(
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 z-[10000] transition-opacity"
        onClick={onClose}
      ></div>

      {/* Modal Content */}
      <div
        className={`fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-2xl shadow-xl z-[10001] w-full ${maxWidth} mx-auto flex flex-col max-h-[90vh] overflow-hidden`}
      >
        {/* Header */}
        {!hideHeader ? (
          <div className="flex-none flex items-center justify-between px-6 py-4 bg-gradient-to-r from-blue-50 via-cyan-50 to-blue-50 border-b border-blue-100">
            <h3 className="text-lg font-bold bg-gradient-to-r from-blue-700 to-cyan-600 bg-clip-text text-transparent">{title || ''}</h3>
            <button
              onClick={onClose}
              className="p-2 rounded-full text-neutral-icon hover:bg-white/80 hover:text-blue-600 transition-all duration-200 hover:shadow-md"
            >
              <FaTimes className="w-5 h-5" />
            </button>
          </div>
        ) : (
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-2 rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-all z-[10002] bg-white/50 backdrop-blur-sm shadow-sm border border-slate-100"
          >
            <FaTimes className="w-5 h-5" />
          </button>
        )}

        {/* Body */}
        <div className={`flex-1 overflow-y-auto ${bodyClassName}`}>
          {children}
        </div>
      </div>
    </>,
    document.body // Render modal in the body to avoid z-index issues
  );
};

export default Modal;
