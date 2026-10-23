import {
  InteractionRequiredAuthError,
  EventType,
  PublicClientApplication,
  type AccountInfo,
  type AuthenticationResult,
} from '@azure/msal-browser'
import { MsalProvider, useMsal } from '@azure/msal-react'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AuthenticationContext, AuthenticationError } from './authentication'

const tenantId = (import.meta.env.VITE_ENTRA_TENANT_ID ?? '').trim()
const clientId = (import.meta.env.VITE_ENTRA_CLIENT_ID ?? '').trim()
const apiScope = (import.meta.env.VITE_API_SCOPE ?? '').trim()
const redirectUri = (import.meta.env.VITE_REDIRECT_URI ?? window.location.origin).trim()

function configured(): boolean {
  return Boolean(tenantId && clientId && apiScope)
}

function MsalAuthenticationBridge({ children }: { children: ReactNode }) {
  const { instance, accounts } = useMsal()
  const [identityRevision, setIdentityRevision] = useState(0)
  const identity = useRef<string | null>(null)
  const accountKey = (account: AccountInfo | null) => account ? JSON.stringify([account.homeAccountId, account.tenantId, account.localAccountId]) : null
  useEffect(() => {
    identity.current = accountKey(instance.getActiveAccount() ?? instance.getAllAccounts()[0] ?? null)
    const id = instance.addEventCallback(event => {
      if (event.eventType === EventType.LOGOUT_START || event.eventType === EventType.LOGOUT_SUCCESS) {
        const hadIdentity = identity.current !== null
        identity.current = null
        if (hadIdentity || event.eventType === EventType.LOGOUT_START) setIdentityRevision(n => n + 1)
      } else if (event.eventType === EventType.LOGIN_SUCCESS || event.eventType === EventType.ACTIVE_ACCOUNT_CHANGED) {
        const account = event.eventType === EventType.LOGIN_SUCCESS
          ? (event.payload as AuthenticationResult).account
          : instance.getActiveAccount()
        const next = accountKey(account)
        // Establishing the first identity must not cancel the login's own caller.
        // Replacing or removing an established identity must discard its workspace.
        if (identity.current !== null && identity.current !== next) setIdentityRevision(n => n + 1)
        identity.current = next
      }
    })
    return () => { if (id) instance.removeEventCallback(id) }
  }, [instance])

  const getAccessToken = useCallback(async (): Promise<string> => {
    try {
      await instance.initialize()
      let account: AccountInfo | null = instance.getActiveAccount() ?? instance.getAllAccounts()[0] ?? null
      if (!account) {
        const login: AuthenticationResult = await instance.loginPopup({
          scopes: [apiScope],
          redirectUri,
          prompt: 'select_account',
        })
        account = login.account
        if (!account) throw new AuthenticationError('Microsoft sign-in returned no account. Retry sign-in.')
        instance.setActiveAccount(account)
        return login.accessToken
      }

      try {
        const result = await instance.acquireTokenSilent({
          account,
          scopes: [apiScope],
          redirectUri,
          forceRefresh: true,
        })
        return result.accessToken
      } catch (error) {
        if (!(error instanceof InteractionRequiredAuthError)) throw error
        const result = await instance.acquireTokenPopup({
          account,
          scopes: [apiScope],
          redirectUri,
        })
        return result.accessToken
      }
    } catch (error) {
      if (error instanceof AuthenticationError) throw error
      const detail = error as { errorCode?: string; errorMessage?: string; correlationId?: string }
      const code = typeof detail?.errorCode === 'string' && /^[a-z0-9_]+$/i.test(detail.errorCode) ? detail.errorCode : 'authentication_failed'
      const aadsts = typeof detail?.errorMessage === 'string' ? detail.errorMessage.match(/AADSTS\d+/)?.[0] : undefined
      const correlation = typeof detail?.correlationId === 'string' && /^[a-f0-9-]{36}$/i.test(detail.correlationId) ? ` Correlation: ${detail.correlationId}.` : ''
      throw new AuthenticationError(`Microsoft sign-in failed (${[code, aadsts].filter(Boolean).join('; ')}). Retry sign-in; if consent or administrator approval is required, contact your operator with this code.${correlation}`)
    }
  }, [instance])

  const signOut = useCallback(async () => {
    await instance.logoutPopup({ account: instance.getActiveAccount() ?? accounts[0], postLogoutRedirectUri: redirectUri })
  }, [instance, accounts])
  const identityKey = `session:${identityRevision}`
  const value = useMemo(() => ({ getAccessToken, signOut, identityKey }), [getAccessToken, signOut, identityKey])
  return <AuthenticationContext.Provider value={value}>{children}</AuthenticationContext.Provider>
}

function ConfiguredAuthenticationProvider({ children }: { children: ReactNode }) {
  const [instance] = useState(
    () =>
      new PublicClientApplication({
        auth: {
          clientId,
          authority: `https://login.microsoftonline.com/${tenantId}`,
          redirectUri,
        },
        cache: {
          cacheLocation: 'memoryStorage',
        },
      }),
  )

  return (
    <MsalProvider instance={instance}>
      <MsalAuthenticationBridge>{children}</MsalAuthenticationBridge>
    </MsalProvider>
  )
}

export function AuthenticationProvider({ children }: { children: ReactNode }) {
  if (!configured()) {
    return (
      <AuthenticationContext.Provider
        value={{
          getAccessToken: async () => null,
        }}
      >
        {children}
      </AuthenticationContext.Provider>
    )
  }

  return <ConfiguredAuthenticationProvider>{children}</ConfiguredAuthenticationProvider>
}
