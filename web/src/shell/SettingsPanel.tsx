import { LogOut, Monitor, Moon, Sun } from 'lucide-react'
import type { Me } from '../api/endpoints'
import type { Theme } from '../app/appearance'

const THEMES: { id: Theme; label: string; icon: typeof Sun }[] = [
  { id: 'auto', label: 'Automatic', icon: Monitor },
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
]

interface Props {
  me?: Me
  theme: Theme
  onTheme: (theme: Theme) => void
  onSignOut: () => void
}

/** Who is signed in (read-only: the directory and the admin decide it), and the theme. */
export function SettingsPanel({ me, theme, onTheme, onSignOut }: Props) {
  const details: [string, string | undefined][] = [
    ['Name', me?.display_name],
    ['Role', me?.role.replace(/_/g, ' ')],
    ['Branch', me?.attributes?.branch],
    ['Staff number', me?.id],
  ]
  return (
    <div className="grid gap-5 p-4">
      <section aria-labelledby="account-heading" className="grid gap-2">
        <h2 id="account-heading" className="text-sm font-semibold">
          Your account
        </h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {details
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-muted">{label}</dt>
                <dd className="m-0 capitalize">{value}</dd>
              </div>
            ))}
        </dl>
        <p className="text-xs text-muted">Your role and branch are set by your administrator.</p>
      </section>

      <fieldset className="grid gap-2 border-0 p-0">
        <legend className="mb-2 text-sm font-semibold">Theme</legend>
        <div className="flex gap-1.5">
          {THEMES.map(({ id, label, icon: Icon }) => (
            <label
              key={id}
              className="flex flex-1 cursor-pointer flex-col items-center gap-1 rounded-lg border border-line py-2 text-xs has-checked:border-accent has-checked:bg-accent-soft"
            >
              <input
                type="radio"
                name="theme"
                value={id}
                checked={theme === id}
                onChange={() => onTheme(id)}
                className="sr-only"
              />
              <Icon aria-hidden className="size-4" />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <button type="button" className="btn-link inline-flex w-fit items-center gap-1.5" onClick={onSignOut}>
        <LogOut aria-hidden className="size-4" /> Sign out
      </button>
    </div>
  )
}
