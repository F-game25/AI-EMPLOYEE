import './SettingsForm.css'

/**
 * <SettingsForm>
 * Reusable form wrapper with consistent styling and error display
 */
export default function SettingsForm({
  children,
  onSubmit,
  className = '',
  style,
}) {
  const handleSubmit = (e) => {
    e.preventDefault()
    if (onSubmit) onSubmit(e)
  }

  return (
    <form
      className={`settings-form ${className}`.trim()}
      onSubmit={handleSubmit}
      style={style}
    >
      {children}
    </form>
  )
}

/**
 * <FormGroup>
 * Wraps a label, input, and error message with consistent spacing
 */
export function FormGroup({
  label,
  error,
  isTouched,
  hint,
  required,
  children,
  className = '',
}) {
  const hasError = isTouched && error
  return (
    <div className={`form-group ${hasError ? 'form-group--error' : ''} ${className}`.trim()}>
      {label && (
        <label className="form-group__label">
          {label}
          {required && <span className="form-group__required">*</span>}
        </label>
      )}
      {children}
      {hint && !hasError && <p className="form-group__hint">{hint}</p>}
      {hasError && <p className="form-group__error">{error}</p>}
    </div>
  )
}

/**
 * <FormSection>
 * Wraps a set of form groups with a title and description
 */
export function FormSection({
  title,
  description,
  children,
  className = '',
}) {
  return (
    <fieldset className={`form-section ${className}`.trim()}>
      {title && <legend className="form-section__title">{title}</legend>}
      {description && <p className="form-section__description">{description}</p>}
      <div className="form-section__content">
        {children}
      </div>
    </fieldset>
  )
}
