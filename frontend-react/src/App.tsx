import { BrowserRouter, Route, Routes } from 'react-router-dom'

import AuthPage from '@/pages/Auth'
import Landing from '@/pages/Landing'
import ProfilePage from '@/pages/Profile'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
