/**
 * Merchant onboarding.
 *
 * Two short steps rather than one long form: the business, then what the person
 * wants to do next. Nothing here is guessed on their behalf — currency and
 * timezone default to sensible values but are shown and editable.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useStartOwnAccount } from '../../auth/useStartOwnAccount'
import { useWorkspace } from '../../auth/WorkspaceProvider'
import { AppShell } from '../../components/AppShell'
import {
  Alert,
  Button,
  Card,
  Field,
  PageHeader,
  Select,
  TextInput,
} from '../../components/ui'
import { createMerchant } from '../../services/privateApi'

const BUSINESS_TYPES = [
  'Retail shop',
  'Kirana / grocery',
  'Cafe or restaurant',
  'Electronics',
  'Apparel and fashion',
  'Pharmacy',
  'Online / D2C store',
  'Services',
  'Other',
]

const CURRENCIES = [
  ['INR', 'Indian Rupee (INR)'],
  ['USD', 'US Dollar (USD)'],
  ['EUR', 'Euro (EUR)'],
  ['GBP', 'Pound Sterling (GBP)'],
  ['AED', 'UAE Dirham (AED)'],
  ['SGD', 'Singapore Dollar (SGD)'],
]

const TIMEZONES = [
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Europe/London',
  'America/New_York',
  'UTC',
]

export default function OnboardingPage() {
  const { readOnly } = useWorkspace()
  if (readOnly) return <ReadOnlyOnboarding />
  return <OnboardingForm />
}

/** The shared demo cannot add businesses; say so before anyone fills a form. */
function ReadOnlyOnboarding() {
  const { start, leaving } = useStartOwnAccount()
  return (
    <AppShell>
      <PageHeader
        eyebrow="Demo account"
        title="Add your own business with your own account"
        description="The demo is shared and read-only, so nothing can be added to it. Create a free account to set up your business, upload your sales data and get your own analysis."
      />
      <div className="mt-8 flex max-w-2xl flex-wrap gap-3">
        <Button variant="gold" onClick={start} disabled={leaving}>
          {leaving ? 'Leaving the demo…' : 'Create your own account'}
        </Button>
        <Button as="link" to="/app" variant="ghost">
          Back to the demo
        </Button>
      </div>
    </AppShell>
  )
}

function OnboardingForm() {
  const navigate = useNavigate()

  const [step] = useState(1)
  const [form, setForm] = useState({
    name: '',
    business_type: BUSINESS_TYPES[0],
    currency: 'INR',
    timezone: 'Asia/Kolkata',
    description: '',
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value })

  async function submit(event) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const result = await createMerchant(form)
      // Straight to the upload wizard: an empty dashboard would tell them
      // nothing, and uploading data is the only thing that changes that.
      navigate(`/app/merchant/${result.merchant.id}/upload`, {
        replace: true,
        state: { justCreated: result.merchant.name },
      })
    } catch (caught) {
      setError(caught.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="Step 1 of 2"
        title="Welcome — tell us about your business"
        description="This names your private workspace and sets how figures are formatted. Next you will upload your data. You can change any of this later."

      />

      <div className="mt-8 max-w-2xl">
        {step === 1 ? (
          <Card>
            <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
              {error && (
                <Alert tone="error" title="Could not create the business">
                  {error}
                </Alert>
              )}

              <Field label="Business name" id="onboard-name">
                <TextInput
                  id="onboard-name"
                  required
                  maxLength={120}
                  value={form.name}
                  onChange={update('name')}
                  placeholder="Riya's Bakery"
                />
              </Field>

              <Field label="Business type" id="onboard-type">
                <Select id="onboard-type" value={form.business_type} onChange={update('business_type')}>
                  {BUSINESS_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </Select>
              </Field>

              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <Field label="Currency" id="onboard-currency">
                  <Select id="onboard-currency" value={form.currency} onChange={update('currency')}>
                    {CURRENCIES.map(([code, label]) => (
                      <option key={code} value={code}>
                        {label}
                      </option>
                    ))}
                  </Select>
                </Field>

                <Field label="Timezone" id="onboard-timezone">
                  <Select id="onboard-timezone" value={form.timezone} onChange={update('timezone')}>
                    {TIMEZONES.map((zone) => (
                      <option key={zone} value={zone}>
                        {zone}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>

              <Field
                label="Description"
                id="onboard-description"
                hint="Optional. A line to remind you what this workspace covers."
              >
                <TextInput
                  id="onboard-description"
                  maxLength={500}
                  value={form.description}
                  onChange={update('description')}
                  placeholder="Main outlet, MG Road"
                />
              </Field>

              <Button type="submit" as="button" disabled={busy || !form.name.trim()}>
                {busy ? 'Creating…' : 'Create workspace'}
              </Button>
            </form>
          </Card>
        ) : null}
      </div>
    </AppShell>
  )
}
