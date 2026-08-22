import { forwardRef, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from 'react';
import './TextField.css';

interface BaseProps {
  label?: string;
  error?: string;
  hint?: string;
  icon?: ReactNode;
}

type TextFieldProps = BaseProps & InputHTMLAttributes<HTMLInputElement>;

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(({ label, error, hint, icon, className = '', id, ...rest }, ref) => {
  const fieldId = id || label?.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className={`field ${error ? 'field--error' : ''} ${className}`}>
      {label && <label htmlFor={fieldId} className="field__label">{label}</label>}
      <div className="field__control">
        {icon && <span className="field__icon">{icon}</span>}
        <input ref={ref} id={fieldId} className={`field__input ${icon ? 'field__input--with-icon' : ''}`} {...rest} />
      </div>
      {error && <span className="field__message field__message--error">{error}</span>}
      {!error && hint && <span className="field__message">{hint}</span>}
    </div>
  );
});
TextField.displayName = 'TextField';

type TextAreaProps = BaseProps & TextareaHTMLAttributes<HTMLTextAreaElement>;

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(({ label, error, hint, className = '', id, ...rest }, ref) => {
  const fieldId = id || label?.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className={`field ${error ? 'field--error' : ''} ${className}`}>
      {label && <label htmlFor={fieldId} className="field__label">{label}</label>}
      <textarea ref={ref} id={fieldId} className="field__textarea" {...rest} />
      {error && <span className="field__message field__message--error">{error}</span>}
      {!error && hint && <span className="field__message">{hint}</span>}
    </div>
  );
});
TextArea.displayName = 'TextArea';
