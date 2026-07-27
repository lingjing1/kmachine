import { useState, useEffect, useRef } from 'react';
import { FaChevronDown } from 'react-icons/fa';

interface CustomSelectOption {
    value: number | string;
    label: string;
}

interface CustomSelectProps {
    value: number | string | null;
    onChange: (val: any) => void;
    options: CustomSelectOption[];
    placeholder: string;
    className?: string;
    disabled?: boolean;
}

const CustomSelect = ({
    value,
    onChange,
    options,
    placeholder,
    className = '',
    disabled = false
}: CustomSelectProps) => {
    const [isOpen, setIsOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    // Close on click outside
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (ref.current && !ref.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const selectedOption = options.find(o => o.value === value);

    const handleToggle = () => {
        if (!disabled) {
            setIsOpen(!isOpen);
        }
    };

    return (
        <div className={`relative w-full ${className}`} ref={ref}>
            <div
                onClick={handleToggle}
                className={`w-full px-2 py-1.5 bg-white border rounded-xl text-sm flex items-center justify-between cursor-pointer transition-all ${isOpen
                        ? 'border-blue-400 ring-2 ring-blue-100'
                        : 'border-gray-200 hover:border-gray-300'
                    } ${disabled ? 'opacity-60 cursor-not-allowed bg-gray-50' : ''}`}
            >
                <span className={`block truncate ${selectedOption ? 'text-gray-700' : 'text-gray-400'}`}>
                    {selectedOption ? selectedOption.label : placeholder}
                </span>
                <FaChevronDown className={`text-gray-400 text-xs transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </div>

            {isOpen && !disabled && (
                <div className="absolute top-full left-0 w-full mt-1 bg-white border border-gray-200 rounded-xl shadow-xl z-50 max-h-60 overflow-y-auto overflow-x-hidden">
                    <div
                        className="px-3 py-2 text-sm text-gray-400 hover:bg-gray-50 cursor-pointer transition-colors"
                        onClick={() => {
                            onChange(null);
                            setIsOpen(false);
                        }}
                    >
                        {placeholder}
                    </div>
                    {options.map((opt) => (
                        <div
                            key={opt.value}
                            className={`px-3 py-2 text-sm cursor-pointer transition-colors truncate ${value === opt.value ? 'bg-blue-50 text-blue-600 font-medium' : 'text-gray-700 hover:bg-gray-50 hover:text-blue-600'
                                }`}
                            onClick={() => {
                                onChange(opt.value);
                                setIsOpen(false);
                            }}
                            title={opt.label}
                        >
                            {opt.label}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default CustomSelect;
