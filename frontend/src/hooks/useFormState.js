import { useState, useCallback } from 'react'

export function useFormState(initialValues = {}, onValidate = null) {
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState({})
  const [touched, setTouched] = useState({})

  const setField = useCallback((key, value) => {
    setValues(v => ({ ...v, [key]: value }))
    // Auto-validate on field change if validation provided
    if (onValidate) {
      const err = onValidate(key, value)
      if (err) {
        setErrors(e => ({ ...e, [key]: err }))
      } else {
        setErrors(e => {
          const newErrs = { ...e }
          delete newErrs[key]
          return newErrs
        })
      }
    }
  }, [onValidate])

  const setError = useCallback((key, message) => {
    if (message) {
      setErrors(e => ({ ...e, [key]: message }))
    } else {
      setErrors(e => {
        const newErrs = { ...e }
        delete newErrs[key]
        return newErrs
      })
    }
  }, [])

  const markTouched = useCallback((key) => {
    setTouched(t => ({ ...t, [key]: true }))
  }, [])

  const reset = useCallback(() => {
    setValues(initialValues)
    setErrors({})
    setTouched({})
  }, [initialValues])

  const isValid = useCallback(() => {
    return Object.keys(errors).length === 0
  }, [errors])

  const getFieldProps = useCallback((key) => {
    return {
      value: values[key] ?? '',
      onChange: (e) => {
        const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value
        setField(key, val)
      },
      onBlur: () => markTouched(key),
    }
  }, [values, setField, markTouched])

  const getFieldState = useCallback((key) => {
    return {
      value: values[key],
      error: errors[key],
      isTouched: touched[key],
      isError: touched[key] && !!errors[key],
    }
  }, [values, errors, touched])

  return {
    values,
    errors,
    touched,
    setField,
    setError,
    markTouched,
    reset,
    isValid,
    getFieldProps,
    getFieldState,
  }
}
