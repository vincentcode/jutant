// The assistant's name and colours for this deployment (from /api/app), and the light or dark
// theme each person chooses. The name is the pack's; the accent colour is the deployment's.

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { appInfo, type AppInfo } from '../api/endpoints'

export const DEFAULT_NAME = 'Staff Assistant'
const HEX = /^#[0-9a-fA-F]{6}$/

/** The deployment's name and accent, applied to the page title and the colour tokens. */
export function useAppInfo(): AppInfo {
  const { data } = useQuery({ queryKey: ['app'], queryFn: appInfo, staleTime: Infinity })
  const name = data?.name || DEFAULT_NAME
  const accent = data?.accent && HEX.test(data.accent) ? data.accent : undefined
  useEffect(() => {
    document.title = name
  }, [name])
  useEffect(() => {
    if (accent) document.documentElement.style.setProperty('--brand', accent)
    else document.documentElement.style.removeProperty('--brand')
  }, [accent])
  return { name, accent: accent ?? null }
}

export type Theme = 'auto' | 'light' | 'dark'
const THEMES: Theme[] = ['auto', 'light', 'dark']
const KEY = 'jutant.theme'

function stored(): Theme {
  try {
    const value = localStorage.getItem(KEY)
    return THEMES.includes(value as Theme) ? (value as Theme) : 'auto'
  } catch {
    return 'auto' // storage can be blocked; the system's choice then applies
  }
}

/** The theme this person chose; "auto" follows the system. Remembered in this browser only.
 * Returns the theme, a function to move to the next one, and one to set it. */
export function useTheme(): [Theme, () => void, (theme: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(stored)
  useEffect(() => {
    if (theme === 'auto') delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      // not remembered, but still applied
    }
  }, [theme])
  const next = () => setTheme((t) => THEMES[(THEMES.indexOf(t) + 1) % THEMES.length] ?? 'auto')
  return [theme, next, setTheme]
}
