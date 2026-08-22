import { forwardRef, SelectHTMLAttributes } from 'react';
import { FiChevronDown } from 'react-icons/fi';
import './Select.css';

export interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  hint?: string;
  options: SelectOption[];
  placeholder?: string;
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, hint, options, placeholder, className = '', id, ...rest }, ref) => {
    const fieldId = id || label?.toLowerCase().replace(/\s+/g, '-');
    return (
      <div className={`ui-select ${error ? 'ui-select--error' : ''} ${className}`}>
        {label && (
          <label htmlFor={fieldId} className="ui-select__label">
            {label}
          </label>
        )}
        <div className="ui-select__control">
          <select ref={ref} id={fieldId} className="ui-select__input" {...rest}>
            {placeholder && (
              <option value="" disabled hidden>
                {placeholder}
              </option>
            )}
            {options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <FiChevronDown className="ui-select__chevron" size={16} />
        </div>
        {error && <span className="ui-select__message ui-select__message--error">{error}</span>}
        {!error && hint && <span className="ui-select__message">{hint}</span>}
      </div>
    );
  }
);
Select.displayName = 'Select';

export default Select;
