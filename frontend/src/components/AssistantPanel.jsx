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
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Ask about this business</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Answers come from this merchant&apos;s own numbers, not from general advice
          </p>
        </div>
        {status && (
          <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
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
          className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition focus:border-teal-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600/30 disabled:cursor-not-allowed disabled:bg-slate-100"
        />
        <button
          type="submit"
          disabled={disabled || loading || !question.trim()}
          className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-teal-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 disabled:cursor-not-allowed disabled:bg-slate-300"
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
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600 transition hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {suggested}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-medium text-red-700">Could not get an answer</p>
          <p className="mt-1 text-sm text-red-700">{error}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 transition hover:bg-red-50"
            >
              Try again
            </button>
          )}
        </div>
      )}

      {!error && answer && (
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-medium text-slate-500">{answer.question}</p>
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-800">
            {answer.answer}
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-200 pt-3">
            <span className="text-xs text-slate-500">
              {answer.source === 'llm'
                ? 'Written by the language model from this merchant’s data'
                : 'Composed directly from this merchant’s data'}
            </span>
            {answer.grounded_in?.length > 0 && (
              <span className="text-xs text-slate-400">
                · based on {answer.grounded_in.join(', ').replaceAll('_', ' ')}
              </span>
            )}
          </div>

          {answer.warnings?.length > 0 && (
            <ul className="mt-2 space-y-1">
              {answer.warnings.map((warning) => (
                <li key={warning} className="text-xs text-amber-700">
                  {warning}
                </li>
              ))}
            </ul>
          )}

          {answer.limitations?.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-medium text-slate-500 hover:text-slate-700">
                What this answer cannot tell you
              </summary>
              <ul className="mt-2 space-y-1">
                {answer.limitations.map((note) => (
                  <li key={note} className="text-xs text-slate-500">
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
