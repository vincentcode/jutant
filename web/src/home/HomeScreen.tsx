import type { ReactNode } from 'react'
import {
  BookOpen,
  FileText,
  Landmark,
  LifeBuoy,
  ListChecks,
  MessageSquare,
  Package,
  ShieldCheck,
  UserRound,
  type LucideIcon,
} from 'lucide-react'
import type { HomeCard } from '../api/endpoints'
import { ConversationList } from '../chat/ConversationList'

// The icons a pack may name for its cards. Kept to a short list so the bundle carries only
// these; an unknown name gets the default.
const ICONS: Record<string, LucideIcon> = {
  landmark: Landmark,
  'user-round': UserRound,
  'book-open': BookOpen,
  'life-buoy': LifeBuoy,
  'file-text': FileText,
  'list-checks': ListChecks,
  package: Package,
  'shield-check': ShieldCheck,
}

interface Props {
  firstName?: string
  cards: HomeCard[]
  onCard: (card: HomeCard) => void
  composer: ReactNode
}

/** The home screen: a greeting, where to start, the question box, and recent conversations. */
export function HomeScreen({ firstName, cards, onCard, composer }: Props) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(ellipse_70%_45%_at_50%_0%,var(--accent-soft),transparent)]">
      <div className="mx-auto grid w-full max-w-4xl gap-8 px-4 py-10 sm:py-14">
        <header className="grid gap-1 text-center">
          <h1 className="text-2xl font-semibold sm:text-3xl">
            {greeting()}
            {firstName ? `, ${firstName}` : ''}
          </h1>
          <p className="text-muted">How can I help you today?</p>
        </header>

        {/* A centred, wrapping row: a role with fewer cards than columns still sits in the middle. */}
        {cards.length > 0 && (
          <ul aria-label="Where to start" className="m-0 flex list-none flex-wrap justify-center gap-3 p-0">
            {cards.map((card) => {
              const Icon = ICONS[card.icon] ?? MessageSquare
              return (
                <li key={card.feature_id} className="w-full sm:w-[calc((100%-0.75rem)/2)] lg:w-[calc((100%-2.25rem)/4)]">
                  <button
                    type="button"
                    onClick={() => onCard(card)}
                    className="grid h-full w-full content-start gap-2 rounded-2xl border border-line bg-surface p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-accent hover:shadow-md"
                  >
                    <span className="flex size-9 items-center justify-center rounded-xl bg-accent-soft text-accent">
                      <Icon aria-hidden className="size-5" />
                    </span>
                    <span className="font-semibold">{card.title}</span>
                    <span className="text-sm text-muted">{card.description}</span>
                    {card.label && <span className="mt-auto pt-1 text-xs font-medium text-accent">{card.label}</span>}
                  </button>
                </li>
              )
            })}
          </ul>
        )}

        <div className="mx-auto w-full max-w-3xl">{composer}</div>

        <section aria-labelledby="recent-heading" className="mx-auto grid w-full max-w-xl gap-2">
          <h2 id="recent-heading" className="text-center text-sm font-semibold text-muted">
            Recent conversations
          </h2>
          <div className="rounded-2xl border border-line bg-surface p-1.5">
            <ConversationList limit={5} />
          </div>
        </section>
      </div>
    </div>
  )
}

export function greeting(now = new Date()): string {
  const hour = now.getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}
