'use strict';

/**
 * Error Recovery & Graceful Degradation
 * Handles agent failures, retries, and fallback strategies
 */

const ERROR_TYPES = {
  TRANSIENT: 'transient',      // Retry
  AGENT_FAILURE: 'agent_failure', // Try alternate agent
  CRITICAL: 'critical',        // Ask user
  VALIDATION: 'validation',    // Partial result with confidence score
};

const RETRY_CONFIG = {
  max_attempts: 3,
  initial_delay_ms: 2000,
  max_delay_ms: 10000,
  backoff_multiplier: 2,
};

class ErrorRecoveryManager {
  constructor() {
    this.errorLog = [];
    this.retryQueue = [];
  }

  /**
   * Classify error and determine recovery action
   */
  classifyError(error, context = {}) {
    const message = error.message || String(error);

    // Transient errors (rate limit, timeout, network)
    if (
      message.includes('rate limit') ||
      message.includes('too many requests') ||
      message.includes('ECONNREFUSED') ||
      message.includes('ENOTFOUND')
    ) {
      return {
        type: ERROR_TYPES.TRANSIENT,
        action: 'retry_with_backoff',
        fallback: 'use_cached',
      };
    }

    // Agent-specific failure
    if (message.includes('agent') || message.includes('execute')) {
      return {
        type: ERROR_TYPES.AGENT_FAILURE,
        action: 'try_alternate_agent',
        fallback: 'return_partial_result',
      };
    }

    // Validation/quality issues
    if (message.includes('validation') || message.includes('confidence')) {
      return {
        type: ERROR_TYPES.VALIDATION,
        action: 'return_partial_with_confidence',
        fallback: 'ask_user',
      };
    }

    // Critical / unknown
    return {
      type: ERROR_TYPES.CRITICAL,
      action: 'ask_user',
      fallback: 'halt',
    };
  }

  /**
   * Build retry strategy with exponential backoff
   */
  buildRetryStrategy(attempt = 0) {
    if (attempt >= RETRY_CONFIG.max_attempts) {
      return null; // No more retries
    }

    const delay = Math.min(
      RETRY_CONFIG.initial_delay_ms * Math.pow(RETRY_CONFIG.backoff_multiplier, attempt),
      RETRY_CONFIG.max_delay_ms
    );

    return {
      attempt: attempt + 1,
      delay_ms: delay,
      next_retry_at: new Date(Date.now() + delay).toISOString(),
      final_attempt: attempt + 1 === RETRY_CONFIG.max_attempts,
    };
  }

  /**
   * Log error for observability
   */
  logError(error, context = {}) {
    const classification = this.classifyError(error, context);
    const entry = {
      timestamp: new Date().toISOString(),
      error_message: error.message || String(error),
      error_code: error.code,
      context,
      classification,
      stack: error.stack,
    };
    this.errorLog.push(entry);

    // Keep last 100 errors
    if (this.errorLog.length > 100) {
      this.errorLog.shift();
    }

    return entry;
  }

  /**
   * Generate user-facing error message
   */
  getUserMessage(error, context = {}) {
    const type = error.type || this.classifyError(error, context).type;

    const messages = {
      [ERROR_TYPES.TRANSIENT]: `The system is temporarily busy. I'll retry this. (Attempt ${context.attempt || 1}/3)`,
      [ERROR_TYPES.AGENT_FAILURE]: `The ${context.agent || 'processing'} agent encountered an issue. Trying an alternate approach...`,
      [ERROR_TYPES.VALIDATION]: `I got some results, but I'm only ${Math.round((context.confidence || 0) * 100)}% confident. Here's what I found:`,
      [ERROR_TYPES.CRITICAL]: `I hit an issue I can't recover from. Can you help me refine the request?`,
    };

    return messages[type] || 'Something went wrong. Let me try again.';
  }

  /**
   * Generate recovery action for chat
   */
  buildRecoveryAction(error, context = {}) {
    const classification = this.classifyError(error, context);
    return {
      user_message: this.getUserMessage(error, context),
      action_type: classification.action,
      action_params: {
        retry_strategy: classification.action === 'retry_with_backoff' ? this.buildRetryStrategy(context.attempt) : null,
        fallback: classification.fallback,
        agent_alternate: context.alternate_agent || null,
      },
      confidence: context.confidence || 0,
      next_step: this.getNextStep(classification),
    };
  }

  /**
   * Determine next step after error
   */
  getNextStep(classification) {
    switch (classification.action) {
      case 'retry_with_backoff':
        return 'Wait and retry automatically in a few seconds';
      case 'try_alternate_agent':
        return 'Try with a different processing approach';
      case 'return_partial_with_confidence':
        return 'Return what we have with confidence scores';
      case 'ask_user':
        return 'Ask user to clarify or adjust the request';
      default:
        return 'Investigate and report to user';
    }
  }

  /**
   * Get recent errors for debugging
   */
  getRecentErrors(limit = 10) {
    return this.errorLog.slice(-limit).reverse();
  }
}

module.exports = ErrorRecoveryManager;
