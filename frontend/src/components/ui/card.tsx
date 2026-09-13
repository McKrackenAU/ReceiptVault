import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-xl border border-pine/10 bg-card p-5 shadow-sm', className)} {...props} />
}

export function Badge({
  tone = 'slate',
  children,
}: {
  tone?: 'moss' | 'amber' | 'slate' | 'copper'
  children: ReactNode
}) {
  const map = {
    moss: 'bg-moss/15 text-moss border-moss/30',
    amber: 'bg-amber/15 text-[#7a5a10] border-amber/30',
    slate: 'bg-slate/10 text-slate border-slate/20',
    copper: 'bg-copper/10 text-copper border-copper/20',
  }
  return <span className={cn('inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold', map[tone])}>{children}</span>
}
