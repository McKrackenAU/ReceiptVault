import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 rounded-md text-sm font-semibold transition-colors disabled:pointer-events-none disabled:opacity-50 min-h-10 px-4',
  {
    variants: {
      variant: {
        default: 'bg-pine text-paper hover:bg-pine-deep',
        copper: 'bg-copper text-white hover:bg-[#8f3f1e]',
        outline: 'border border-pine/20 bg-card text-ink hover:bg-paper',
        ghost: 'text-paper hover:bg-white/10',
        danger: 'bg-[#8b2e2e] text-white hover:bg-[#6f2222]',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export function Button({
  className,
  variant,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>) {
  return <button className={cn(buttonVariants({ variant }), className)} {...props} />
}
