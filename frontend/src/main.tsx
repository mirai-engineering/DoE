import React, { useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider, SignedIn, SignedOut, UserButton, useAuth } from '@clerk/clerk-react'
import App from './App.tsx'
import { LandingPage } from './components/LandingPage.tsx'
import { setAuthTokenProvider } from './lib/api.ts'
import './index.css'

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

function AuthenticatedApp() {
  const { getToken } = useAuth()

  useEffect(() => {
    setAuthTokenProvider(() => getToken({ template: 'jwt-doe-template' }))
    return () => setAuthTokenProvider(null)
  }, [getToken])

  return (
    <>
      <div className="fixed right-4 top-4 z-[100] rounded-full border border-white/70 bg-white/80 p-2 shadow-lg backdrop-blur">
        <UserButton afterSignOutUrl="/" />
      </div>
      <App />
    </>
  )
}

const app = clerkPublishableKey ? (
  <ClerkProvider publishableKey={clerkPublishableKey}>
    <SignedIn>
      <AuthenticatedApp />
    </SignedIn>
    <SignedOut>
      <LandingPage />
    </SignedOut>
  </ClerkProvider>
) : (
  <App />
)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{app}</React.StrictMode>,
)
