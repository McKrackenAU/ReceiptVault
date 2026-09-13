import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label } from '@/components/ui/input'
import { api, setCsrf } from '@/lib/api'

export function LoginPage() {
  const navigate = useNavigate()
  const [setup, setSetup] = useState<boolean | null>(null)
  const [error, setError] = useState('')
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')

  useEffect(() => {
    api<{ required: boolean }>('/api/v1/auth/setup-required').then((r) => setSetup(r.required))
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      if (setup) {
        const r = await api<{ csrf: string }>('/api/v1/auth/setup', {
          method: 'POST',
          body: JSON.stringify({ username, email, password, timezone: 'Australia/Melbourne' }),
        })
        setCsrf(r.csrf)
        navigate('/settings?wizard=1')
      } else {
        const r = await api<{ csrf: string }>('/api/v1/auth/login', {
          method: 'POST',
          body: JSON.stringify({ username, password, totp: totp || undefined }),
        })
        setCsrf(r.csrf)
        navigate('/')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to continue')
    }
  }

  if (setup === null) return <p className="p-8">Checking first-run status…</p>

  return (
    <div className="mx-auto flex min-h-screen max-w-lg items-center p-4">
      <Card className="w-full">
        <h1 className="font-serif text-3xl text-pine">{setup ? 'Create the owner account' : 'Sign in to ReceiptVault'}</h1>
        <p className="mt-2 text-sm text-slate">
          Single-owner, self-hosted locker. No public registration. After setup, this page is login only.
        </p>
        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <div>
            <Label htmlFor="username">Username</Label>
            <Input id="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </div>
          {setup && (
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
          )}
          <div>
            <Label htmlFor="password">Password (12+ characters)</Label>
            <Input id="password" type="password" minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          {!setup && (
            <div>
              <Label htmlFor="totp">Authenticator code (if enabled)</Label>
              <Input id="totp" inputMode="numeric" value={totp} onChange={(e) => setTotp(e.target.value)} />
            </div>
          )}
          {error && <p className="text-sm text-copper" role="alert">{error}</p>}
          <Button type="submit">{setup ? 'Create owner and continue' : 'Sign in'}</Button>
        </form>
      </Card>
    </div>
  )
}
