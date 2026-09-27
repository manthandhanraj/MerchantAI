/**
 * Account settings: name, password, and removing a business.
 *
 * Deletion is stated plainly and confirmed by typing the business name, because
 * it removes uploads, analyses, reports and the stored files behind them, and
 * none of that can be brought back.
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AppShell } from '../../components/AppShell'
import { useAuth } from '../../auth/AuthProvider'
import { useWorkspace } from '../../auth/WorkspaceProvider'
import {
  Alert,
  Button,
  Card,
  Field,
  PageHeader,
  Spinner,
  TextInput,
} from '../../components/ui'
import { deleteMerchant, getMe, listMerchants, updateMe } from '../../services/privateApi'

export default function AccountPage() {
  const { user, updatePassword, canDeleteAccount, deleteAccount } = useAuth()
  const { readOnly } = useWorkspace()
  const navigate = useNavigate()

  const [profile, setProfile] = useState(null)
  const [merchants, setMerchants] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [fullName, setFullName] = useState('')
  const [savingName, setSavingName] = useState(false)

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [savingPassword, setSavingPassword] = useState(false)

  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)

  const [notice, setNotice] = useState(null)

  const [closing, setClosing] = useState(false)
  const [closeConfirm, setCloseConfirm] = useState('')
  const [closingBusy, setClosingBusy] = useState(false)

  const load = useCallback(async (signal) => {
    setLoading(true)
    setError(null)
    try {
      const [me, list] = await Promise.all([getMe({ signal }), listMerchants({ signal })])
      if (signal?.aborted) return
      setProfile(me.profile)
      setFullName(me.profile?.full_name ?? '')
      setMerchants(list.merchants ?? [])
    } catch (caught) {
      if (!signal?.aborted) setError(caught.message)
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  async function saveName(event) {
    event.preventDefault()
    setSavingName(true)
    setNotice(null)
    try {
      const body = await updateMe(fullName)
      setProfile(body.profile)
      setNotice({ tone: 'success', text: 'Your name has been updated.' })
    } catch (caught) {
      setNotice({ tone: 'error', text: caught.message })
    } finally {
      setSavingName(false)
    }
  }

  async function savePassword(event) {
    event.preventDefault()
    if (password !== confirm || passwordTooShort) return
    setSavingPassword(true)
    setNotice(null)
    try {
      await updatePassword(password)
      setPassword('')
      setConfirm('')
      setNotice({ tone: 'success', text: 'Your password has been changed.' })
    } catch (caught) {
      setNotice({ tone: 'error', text: caught.message })
    } finally {
      setSavingPassword(false)
    }
  }

  async function removeMerchant() {
    if (!deleteTarget || deleteConfirmText !== deleteTarget.name) return
    setDeleting(true)
    setNotice(null)
    try {
      await deleteMerchant(deleteTarget.id)
      setMerchants((current) => current.filter((row) => row.id !== deleteTarget.id))
      setDeleteTarget(null)
      setDeleteConfirmText('')
      setNotice({ tone: 'success', text: 'That business and all of its data have been deleted.' })
    } catch (caught) {
      setNotice({ tone: 'error', text: caught.message })
    } finally {
      setDeleting(false)
    }
  }

  async function closeAccount() {
    if (closeConfirm !== 'DELETE') return
    setClosingBusy(true)
    setNotice(null)
    try {
      await deleteAccount()
      navigate('/login', { replace: true })
    } catch (caught) {
      setNotice({ tone: 'error', text: caught.message })
      setClosingBusy(false)
    }
  }

  if (loading) {
    return (
      <AppShell>
        <Spinner label="Loading your account…" />
      </AppShell>
    )
  }

  const passwordMismatch = confirm.length > 0 && confirm !== password
  const passwordTooShort =
    password.length > 0 &&
    (password.length < 8 || !/[a-zA-Z]/.test(password) || !/\d/.test(password))

  return (
    <AppShell merchants={merchants}>
      <PageHeader
        eyebrow="Account"
        title="Your account"
        description="Your details, your password, and control over the data you have uploaded."
      />

      {error && (
        <div className="mt-5">
          <Alert tone="error" title="Could not load your account">
            {error}
          </Alert>
        </div>
      )}
      {notice && (
        <div className="mt-5">
          <Alert tone={notice.tone}>{notice.text}</Alert>
        </div>
      )}

      <div className="mt-8 grid max-w-3xl grid-cols-1 gap-5">
        <Card>
          <h2 className="text-sm font-semibold text-cream">Your details</h2>
          <form onSubmit={saveName} className="mt-4 flex flex-col gap-4">
            <Field label="Email" id="account-email" hint="Contact support to change this.">
              <TextInput id="account-email" value={user?.email ?? ''} disabled />
            </Field>
            <Field label="Name" id="account-name">
              <TextInput
                id="account-name"
                value={fullName}
                maxLength={120}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Your name"
              />
            </Field>
            <Button
              type="submit"
              as="button"
              disabled={readOnly || savingName || fullName === (profile?.full_name ?? '')}
              className="w-fit"
            >
              {savingName ? 'Saving…' : 'Save'}
            </Button>
          </form>
        </Card>

        {readOnly ? (
          <Card>
            <h2 className="text-sm font-semibold text-cream">Change your password</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              The demo account is shared, so its password cannot be changed here — otherwise the
              next visitor would be locked out. Create your own workspace to manage a real
              account.
            </p>
            <div className="mt-4">
              <Button as="link" to="/signup">
                Create your own workspace
              </Button>
            </div>
          </Card>
        ) : (
        <Card>
          <h2 className="text-sm font-semibold text-cream">Change your password</h2>
          <form onSubmit={savePassword} className="mt-4 flex flex-col gap-4">
            <Field
              label="New password"
              id="account-password"
              hint="At least 8 characters, with a letter and a number."
              error={
                passwordTooShort ? 'Use 8 or more characters, including a letter and a number.' : null
              }
            >
              <TextInput
                id="account-password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
            <Field
              label="Confirm new password"
              id="account-password-confirm"
              error={passwordMismatch ? 'The two passwords do not match.' : null}
            >
              <TextInput
                id="account-password-confirm"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
              />
            </Field>
            <Button
              type="submit"
              as="button"
              disabled={savingPassword || !password || passwordMismatch || passwordTooShort}
              className="w-fit"
            >
              {savingPassword ? 'Updating…' : 'Update password'}
            </Button>
          </form>
        </Card>
        )}

        <Card>
          <h2 className="text-sm font-semibold text-cream">Your data</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Uploaded files and generated reports are stored privately and are readable only by
            your account. Deleting a business removes its uploads, analyses, reports and the
            stored files behind them. This cannot be undone.
          </p>

          {merchants.length === 0 ? (
            <p className="mt-4 text-sm text-faint">You have no businesses set up.</p>
          ) : (
            <ul className="mt-4 divide-y divide-white/5">
              {merchants.map((merchant) => (
                <li key={merchant.id} className="py-3">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    <div className="min-w-0">
                      <p className="text-sm text-cream">{merchant.name}</p>
                      <p className="text-xs text-faint">
                        {merchant.business_type || 'Business'} · {merchant.currency}
                      </p>
                    </div>
                    <div className="ml-auto">
                      {readOnly ? (
                        <span className="text-xs text-faint">Read-only in demo mode</span>
                      ) : (
                        <Button
                          variant="danger"
                          className="px-4 py-2 text-xs"
                          onClick={() => {
                            setDeleteTarget(merchant)
                            setDeleteConfirmText('')
                          }}
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </div>

                  {deleteTarget?.id === merchant.id && (
                    <div className="mt-3 rounded-xl border border-alert/25 bg-alert/8 p-4">
                      <p className="text-sm text-alert">
                        This permanently deletes <strong>{merchant.name}</strong>, every file you
                        uploaded for it, every analysis and every report.
                      </p>
                      <label
                        htmlFor="confirm-delete"
                        className="mt-3 block text-xs text-muted"
                      >
                        Type <span className="font-semibold text-cream">{merchant.name}</span> to
                        confirm.
                      </label>
                      <TextInput
                        id="confirm-delete"
                        className="mt-2"
                        value={deleteConfirmText}
                        onChange={(event) => setDeleteConfirmText(event.target.value)}
                      />
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button
                          variant="danger"
                          className="px-4 py-2 text-xs"
                          disabled={deleting || deleteConfirmText !== merchant.name}
                          onClick={removeMerchant}
                        >
                          {deleting ? 'Deleting…' : 'Delete permanently'}
                        </Button>
                        <Button
                          variant="quiet"
                          className="px-3 py-2 text-xs"
                          onClick={() => setDeleteTarget(null)}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {canDeleteAccount && !readOnly ? (
            <div className="mt-6 border-t border-white/8 pt-5">
              <h3 className="text-sm font-semibold text-cream">Delete my account</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">
                Permanently removes your sign-in, every business, every upload, every analysis and
                every report, including the stored files. This cannot be undone.
              </p>
              {closing ? (
                <div className="mt-3 rounded-xl border border-alert/25 bg-alert/8 p-4">
                  <label htmlFor="close-account" className="block text-xs text-muted">
                    Type <span className="font-semibold text-cream">DELETE</span> to confirm.
                  </label>
                  <TextInput
                    id="close-account"
                    className="mt-2"
                    value={closeConfirm}
                    onChange={(event) => setCloseConfirm(event.target.value)}
                  />
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      variant="danger"
                      className="px-4 py-2 text-xs"
                      disabled={closingBusy || closeConfirm !== 'DELETE'}
                      onClick={closeAccount}
                    >
                      {closingBusy ? 'Deleting…' : 'Delete my account permanently'}
                    </Button>
                    <Button
                      variant="quiet"
                      className="px-3 py-2 text-xs"
                      onClick={() => {
                        setClosing(false)
                        setCloseConfirm('')
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  variant="danger"
                  className="mt-3 px-4 py-2 text-xs"
                  onClick={() => setClosing(true)}
                >
                  Delete my account
                </Button>
              )}
            </div>
          ) : (
            !readOnly && (
              <p className="mt-5 text-xs leading-relaxed text-faint">
                To delete your whole account, delete each business first, then ask the
                administrator to remove your sign-in. Every record and file linked to it is removed
                with it.
              </p>
            )
          )}
        </Card>
      </div>
    </AppShell>
  )
}
