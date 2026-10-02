import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium font-body transition-all duration-300 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        glass:
          'liquid-glass text-foreground hover:scale-[1.04] active:scale-[0.98]',
        primary:
          'bg-foreground text-background hover:scale-[1.04] active:scale-[0.98] shadow-[0_8px_30px_-8px_rgba(255,255,255,0.25)]',
        ghost: 'text-muted-foreground hover:text-foreground',
      },
      size: {
        default: 'h-11 px-6',
        lg: 'h-14 px-9 text-base',
        sm: 'h-9 px-4 text-xs',
      },
    },
    defaultVariants: {
      variant: 'glass',
      size: 'default',
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : 'button'
  return (
    <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />
  )
}

export { Button, buttonVariants }
