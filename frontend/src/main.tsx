import React, { useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider, SignedIn, SignedOut, SignInButton, SignUpButton, UserButton, useAuth } from '@clerk/clerk-react'
import App from './App.tsx'
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

function SignedOutLanding() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#eef0ea] text-slate-950">
      <div className="pointer-events-none fixed inset-0">
        <div className="absolute -left-32 top-[-18rem] h-[34rem] w-[34rem] rounded-full bg-[#d4c3a3]/70 blur-3xl" />
        <div className="absolute right-[-12rem] top-36 h-[32rem] w-[32rem] rounded-full bg-[#526949]/25 blur-3xl" />
        <div className="absolute inset-x-0 bottom-0 h-72 bg-gradient-to-t from-[#dfe4d7] to-transparent" />
      </div>
      <section className="relative mx-auto flex min-h-screen max-w-4xl flex-col items-center justify-center gap-8 px-6 text-center">
        <img src="/assets/doe_logo.png" alt="Mirai DoE" className="h-36 w-36 rounded-3xl border border-slate-200 bg-white object-contain shadow-sm" />
        <div>
          <p className="mb-4 text-xs font-semibold uppercase tracking-[0.28em] text-slate-600">ML-guided DoE platform</p>
          <h1 className="text-5xl font-semibold tracking-[-0.06em] sm:text-6xl">Mirai DoE Engine</h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg leading-8 text-slate-600">
            Sign in to access project, data, model quality, prediction, recommendation, and optimization workflows.
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <SignUpButton mode="modal">
            <button className="rounded-full bg-slate-950 px-8 py-4 text-sm font-semibold uppercase tracking-[0.18em] text-white shadow-xl transition hover:bg-[#526949]">
              Sign up
            </button>
          </SignUpButton>
          <SignInButton mode="modal">
            <button className="rounded-full border border-slate-300 bg-white/80 px-8 py-4 text-sm font-semibold uppercase tracking-[0.18em] text-slate-950 shadow-lg transition hover:border-[#526949] hover:text-[#526949]">
              Sign in
            </button>
          </SignInButton>
        </div>
      </section>
    </main>
  )
}

const app = clerkPublishableKey ? (
  <ClerkProvider publishableKey={clerkPublishableKey}>
    <SignedIn>
      <AuthenticatedApp />
    </SignedIn>
    <SignedOut>
      <SignedOutLanding />
    </SignedOut>
  </ClerkProvider>
) : (
  <App />
)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{app}</React.StrictMode>,
)
