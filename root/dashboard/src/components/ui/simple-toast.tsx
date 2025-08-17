"use client"

import * as React from "react"
import { CheckCircle, XCircle, AlertCircle, X } from "lucide-react"
import { cn } from "@/lib/utils"

export interface SimpleToastProps {
  type?: "success" | "error" | "warning" | "info"
  title?: string
  message: string
  duration?: number
  onClose?: () => void
}

export function SimpleToast({ 
  type = "info", 
  title, 
  message, 
  duration = 4000, 
  onClose 
}: SimpleToastProps) {
  const [isVisible, setIsVisible] = React.useState(true)

  React.useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        setIsVisible(false)
        setTimeout(() => onClose?.(), 300)
      }, duration)

      return () => clearTimeout(timer)
    }
  }, [duration, onClose])

  const getIcon = () => {
    switch (type) {
      case "success":
        return <CheckCircle className="h-5 w-5 text-green-600" />
      case "error":
        return <XCircle className="h-5 w-5 text-red-600" />
      case "warning":
        return <AlertCircle className="h-5 w-5 text-yellow-600" />
      default:
        return <AlertCircle className="h-5 w-5 text-blue-600" />
    }
  }

  const getStyles = () => {
    switch (type) {
      case "success":
        return "bg-green-50 border-green-200 text-green-800"
      case "error":
        return "bg-red-50 border-red-200 text-red-800"
      case "warning":
        return "bg-yellow-50 border-yellow-200 text-yellow-800"
      default:
        return "bg-blue-50 border-blue-200 text-blue-800"
    }
  }

  if (!isVisible) return null

  return (
    <div
      className={cn(
        "fixed top-4 right-4 z-50 w-96 rounded-lg border p-4 shadow-lg transition-all duration-300",
        getStyles(),
        isVisible ? "translate-x-0 opacity-100" : "translate-x-full opacity-0"
      )}
    >
      <div className="flex items-start gap-3">
        {getIcon()}
        <div className="flex-1 min-w-0">
          {title && (
            <div className="text-sm font-semibold mb-1">
              {title}
            </div>
          )}
          <div className="text-sm">
            {message}
          </div>
        </div>
        <button
          onClick={() => {
            setIsVisible(false)
            setTimeout(() => onClose?.(), 300)
          }}
          className="flex-shrink-0 opacity-70 hover:opacity-100 transition-opacity"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

// Simple toast manager
let toastId = 0

export function showToast(props: Omit<SimpleToastProps, 'onClose'>) {
  const id = ++toastId
  const container = document.createElement('div')
  container.id = `toast-${id}`
  document.body.appendChild(container)

  const root = (window as any).ReactDOM?.createRoot?.(container) || (window as any).ReactDOM?.render

  const handleClose = () => {
    if (root?.unmount) {
      root.unmount()
    } else {
      (window as any).ReactDOM?.unmountComponentAtNode?.(container)
    }
    document.body.removeChild(container)
  }

  const ToastComponent = () => (
    <SimpleToast {...props} onClose={handleClose} />
  )

  if (root?.render) {
    root.render(<ToastComponent />)
  } else {
    (window as any).ReactDOM?.render?.(<ToastComponent />, container)
  }
}
