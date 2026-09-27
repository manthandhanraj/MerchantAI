/**
 * Application routes.
 *
 * Two modes sit side by side. `/demo` is the original public dashboard over the
 * committed synthetic dataset and needs no account — it is deliberately left
 * exactly as it was. Everything under `/app` requires a verified session and
 * shows only the signed-in user's own businesses.
 */
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AuthProvider } from './auth/AuthProvider'
import { RequireAnon, RequireAuth } from './auth/ProtectedRoute'
import DashboardPage from './pages/DashboardPage'
import LandingPage from './pages/LandingPage'
import NotFoundPage from './pages/NotFoundPage'
import AccountPage from './pages/app/AccountPage'
import MerchantDashboardPage from './pages/app/MerchantDashboardPage'
import OnboardingPage from './pages/app/OnboardingPage'
import ReportsPage from './pages/app/ReportsPage'
import UploadWizardPage from './pages/app/UploadWizardPage'
import WorkspacePage from './pages/app/WorkspacePage'
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage'
import LoginPage from './pages/auth/LoginPage'
import ResetPasswordPage from './pages/auth/ResetPasswordPage'
import SignupPage from './pages/auth/SignupPage'

export function AppRoutes() {
  return (
    <Routes>
      {/* The product starts at sign-in. The marketing page is still reachable
          from a secondary link, but it is not what the door opens onto. */}
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/about" element={<LandingPage />} />
      <Route path="/demo" element={<DashboardPage />} />

      {/* Signed out only */}
      <Route element={<RequireAnon />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      </Route>

      {/* Reached from an emailed link, which carries its own recovery session,
          so it must not be behind either guard. */}
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      {/* Private workspace — Supabase accounts or built-in accounts, the same
          screens either way. */}
      <Route element={<RequireAuth />}>
        <Route path="/app" element={<WorkspacePage />} />
        <Route path="/app/onboarding" element={<OnboardingPage />} />
        <Route path="/app/merchant/:id" element={<MerchantDashboardPage />} />
        <Route path="/app/merchant/:id/upload" element={<UploadWizardPage />} />
        <Route path="/app/merchant/:id/reports" element={<ReportsPage />} />
        <Route path="/app/account" element={<AccountPage />} />
      </Route>

      {/* The old single-page entry point kept working for anyone with it bookmarked. */}
      <Route path="/dashboard" element={<Navigate to="/demo" replace />} />

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
