import Modal from './Modal';
import Button from './Button';
import { FaExclamationCircle, FaInfoCircle } from 'react-icons/fa';

interface ConfirmDialogProps {
    isOpen: boolean;
    title: string;
    message: React.ReactNode;
    confirmText?: string;
    cancelText?: string;
    onConfirm: () => void;
    onCancel: () => void;
    onClose?: () => void; // Optional separate handler for background/X click
    variant?: 'danger' | 'warning';
}

function ConfirmDialog({
    isOpen,
    title,
    message,
    confirmText = '確認',
    cancelText = '取消',
    onConfirm,
    onCancel,
    onClose, // Optional
    variant = 'warning'
}: ConfirmDialogProps) {


    const Icon = variant === 'danger' ? FaExclamationCircle : FaInfoCircle;

    return (
        <Modal isOpen={isOpen} onClose={onClose || onCancel} title={title}>
            <div className="space-y-6 py-2">
                <div className="flex items-start gap-4 px-2">
                    <div className={`shrink-0 p-3 rounded-full mt-1 ${variant === 'danger' ? 'bg-rose-100' : 'bg-amber-100'}`}>
                        <Icon className={`${variant === 'danger' ? 'text-rose-500' : 'text-amber-500'}`} size={24} />
                    </div>
                    <div className="text-neutral-text-main text-base leading-relaxed font-medium text-left flex-1 whitespace-pre-wrap">{message}</div>
                </div>

                <div className="flex justify-end gap-3 pt-2">
                    <Button
                        variant="secondary"
                        onClick={onCancel}
                        idleText={cancelText}
                    />
                    <Button
                        variant="primary"
                        onClick={onConfirm}
                        idleText={confirmText}
                    />
                </div>
            </div>
        </Modal>
    );
}

export default ConfirmDialog;
