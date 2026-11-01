import { BrowserRouter, Route, Routes } from 'react-router-dom'

import AuthPage from '@/pages/Auth'
import Landing from '@/pages/Landing'
import PrivacyPage from '@/pages/Privacy'
import ProfilePage from '@/pages/Profile'
import ResetPasswordPage from '@/pages/ResetPassword'
import VerifyEmailPage from '@/pages/VerifyEmail'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
