/**
 * AI business assistant (Stage 6).
 *
 * The assistant answers from the merchant's own computed analytics. With the
 * language model disabled — the default — answers are composed directly from
 * that data, which is why the panel says where each answer came from rather
 * than implying a model is always involved.
 */
import { useState } from 'react'

export function AssistantPanel({
  status,
  answer,
  loading,
  error,
  onAsk,
  onRetry,
  disabled,
}) {
  const [question, setQuestion] = useState('')
  const suggestions = answer?.suggested_questions ?? status?.suggested_questions ?? []

  function submit(event) {
    event.preventDefault()
    const trimmed = question.trim()
    if (trimmed && !loading) onAsk(trimmed)
  }

  function askSuggested(suggested) {
    setQuestion(suggested)
    if (!loading) onAsk(suggested)
  }

  return (
    <section className="pulse-lift rounded-2xl border border-white/8 bg-gradient-to-b from-raised to-surface p-4 shadow-[0_12px_30px_rgb(0_0_0/0.25)] sm:p-5">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-cream">Ask about this business</h3>
          <p className="mt-0.5 text-xs text-faint">
            Answers come from this merchant&apos;s own numbers, not from general advice
          </p>
        </div>
        {status && (
          <span className="inline-flex items-center rounded-full bg-white/5 px-2 py-0.5 text-xs font-medium text-muted">
            {status.enabled ? 'Language model on' : 'Answering from data'}
          </span>
        )}
      </header>

      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor="assistant-question" className="sr-only">
          Your question
        </label>
        <input
          id="assistant-question"
          type="text"
          value={question}
          disabled={disabled}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="e.g. Why did my sales decrease?"
          maxLength={500}
          className="flex-1 rounded-lg border border-white/12 bg-white/5 px-3 py-2 text-sm text-cream shadow-sm transition focus:border-sage/70 disabled:cursor-not-allowed disabled:bg-white/4"
        />
        <button
          type="submit"
          disabled={disabled || loading || !question.trim()}
          className="rounded-lg bg-sage px-4 py-2 text-sm font-medium text-[#11251a] shadow-sm transition hover:bg-[#c8eeb0] disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-faint"
        >
          {loading ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {suggestions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {suggestions.map((suggested) => (
            <button
              key={suggested}
              type="button"
              disabled={disabled || loading}
              onClick={() => askSuggested(suggested)}
              className="rounded-full border border-white/8 bg-white/4 px-3 py-1 text-xs text-muted transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {suggested}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div role="alert" className="mt-4 rounded-lg border border-alert/25 bg-alert/8 p-4">
          <p className="text-sm font-medium text-alert">Could not get an answer</p>
          <p className="mt-1 text-sm text-alert">{error}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 rounded-lg border border-alert/30 bg-white/5 px-3 py-1.5 text-sm font-medium text-alert transition hover:bg-alert/10"
            >
              Try again
            </button>
          )}
        </div>
      )}

      {!error && answer && (
        <div className="mt-4 rounded-xl border border-white/8 bg-white/4 p-4">
          <p className="text-xs font-medium text-faint">{answer.question}</p>
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-cream">
            {answer.answer}
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/8 pt-3">
            <span className="text-xs text-faint">
              {answer.source === 'llm'
                ? 'Written by the language model from this merchant’s data'
                : 'Composed directly from this merchant’s data'}
            </span>
            {answer.grounded_in?.length > 0 && (
              <span className="text-xs text-faint">
                · based on {answer.grounded_in.join(', ').replaceAll('_', ' ')}
              </span>
            )}
          </div>

          {answer.warnings?.length > 0 && (
            <ul className="mt-2 space-y-1">
              {answer.warnings.map((warning) => (
                <li key={warning} className="text-xs text-gold">
                  {warning}
                </li>
              ))}
            </ul>
          )}

          {answer.limitations?.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-medium text-faint hover:text-muted">
                What this answer cannot tell you
              </summary>
              <ul className="mt-2 space-y-1">
                {answer.limitations.map((note) => (
                  <li key={note} className="text-xs text-faint">
                    {note}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  )
}
