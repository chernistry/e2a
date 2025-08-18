/**
 * Root Layout Component for Octup E²A Dashboard
 * 
 * This component provides the root layout structure for the entire application,
 * including theme management, providers, and global styling. It handles:
 * - Theme switching (light/dark/system) with cookie persistence
 * - Global providers and context setup
 * - Top loader for navigation feedback
 * - Responsive design and accessibility features
 * 
 * @fileoverview Main layout wrapper for the E²A dashboard application
 * @author E²A Team
 * @version 1.0.0
 */

import Providers from '@/components/layout/providers';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { fontVariables } from '@/lib/font';
import ThemeProvider from '@/components/layout/ThemeToggle/theme-provider';
import { cn } from '@/lib/utils';
import type { Metadata, Viewport } from 'next';
import { cookies } from 'next/headers';
import NextTopLoader from 'nextjs-toploader';
import React from 'react';
import './globals.css';
import './theme.css';

/**
 * Theme color configuration for meta tags
 * Provides appropriate theme colors for light and dark modes
 * These colors are used in the browser's address bar and system UI
 */
const META_THEME_COLORS = {
  light: '#ffffff',  // Pure white for light theme
  dark: '#09090b'    // Very dark gray for dark theme
} as const;

/**
 * Application metadata for SEO and browser display
 * Defines the title, description, and other meta information
 * This metadata is used by search engines and social media platforms
 */
export const metadata: Metadata = {
  title: 'Octup E²A Dashboard',
  description: 'SLA Radar + Invoice Guard with AI Exception Analyst - Real-time monitoring and intelligent exception handling for logistics operations',
  keywords: ['logistics', 'SLA monitoring', 'AI analytics', 'exception handling', 'dashboard'],
  authors: [{ name: 'E²A Team' }],
  viewport: 'width=device-width, initial-scale=1',
  robots: 'index, follow'
};

/**
 * Viewport configuration for responsive design
 * Sets theme color and ensures proper mobile rendering
 * Controls how the page is displayed on different screen sizes
 */
export const viewport: Viewport = {
  themeColor: META_THEME_COLORS.light,
  width: 'device-width',
  initialScale: 1,
  maximumScale: 5,
  userScalable: true
};

/**
 * Root layout component that wraps the entire application
 * 
 * This component:
 * - Manages theme state and persistence via cookies
 * - Sets up global providers and context
 * - Handles responsive design and accessibility
 * - Provides consistent styling across all pages
 * 
 * @param props - Component props
 * @param props.children - React nodes to render within the layout
 * @returns Root layout JSX element
 * 
 * @example
 * ```tsx
 * <RootLayout>
 *   <YourPageContent />
 * </RootLayout>
 * ```
 */
export default async function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  // Get theme preference from cookies for server-side rendering
  // This ensures the theme is consistent between server and client
  const cookieStore = await cookies();
  const activeThemeValue = cookieStore.get('active_theme')?.value;
  
  // Check if theme has scaling applied (accessibility feature)
  // This allows users to scale the UI for better readability
  const isScaled = activeThemeValue?.endsWith('-scaled');

  return (
    <html lang='en' className="h-full" suppressHydrationWarning>
      <head>
        {/* 
          Client-side theme detection script
          This script runs before React hydration to prevent theme flashing
          It detects the user's preferred theme and sets the meta theme-color accordingly
          
          The script:
          1. Checks localStorage for saved theme preference
          2. Falls back to system preference if no saved theme
          3. Updates the meta theme-color to prevent visual flicker
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                if (localStorage.theme === 'dark' || ((!('theme' in localStorage) || localStorage.theme === 'system') && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                  document.querySelector('meta[name="theme-color"]').setAttribute('content', '${META_THEME_COLORS.dark}')
                }
              } catch (_) {}
            `
          }}
        />
      </head>
      
      {/* 
        Body element with dynamic theme classes
        - bg-background: Sets the base background color
        - h-full: Ensures full height layout
        - font-sans antialiased: Clean, readable typography
        - theme-{activeThemeValue}: Applies current theme
        - theme-scaled: Applies accessibility scaling if enabled
      */}
      <body
        className={cn(
          'bg-background h-full font-sans antialiased',
          activeThemeValue ? `theme-${activeThemeValue}` : '',
          isScaled ? 'theme-scaled' : '',
          fontVariables
        )}
      >
        {/* 
          Top loader for navigation feedback
          Shows progress bar during page transitions
          Provides visual feedback that navigation is in progress
        */}
        <NextTopLoader showSpinner={false} />
        
        {/* 
          Theme provider for managing light/dark mode
          Handles system preference detection and theme switching
          
          Configuration:
          - attribute='class': Uses CSS classes for theme switching
          - defaultTheme='system': Respects user's system preference
          - enableSystem: Allows system preference detection
          - disableTransitionOnChange: Prevents animation flicker
          - enableColorScheme: Enables CSS color-scheme support
        */}
        <ThemeProvider
          attribute='class'
          defaultTheme='system'
          enableSystem
          disableTransitionOnChange
          enableColorScheme
        >
          {/* 
            Global providers wrapper
            Includes authentication, state management, and other context providers
            
            The Providers component:
            - Sets up authentication context
            - Manages global application state
            - Provides theme context to child components
            - Handles user preferences and settings
          */}
          <Providers activeThemeValue={activeThemeValue as string}>
            {/* 
              Tooltip provider for global tooltip support
              Enables tooltips throughout the application with consistent styling
            */}
            <TooltipProvider delayDuration={300}>
              {/* 
                Toast notifications for user feedback
                Provides non-intrusive notifications for:
                - Success messages
                - Error alerts
                - Information updates
                - User actions confirmation
              */}
              <Toaster />
              
              {/* 
                Main application content
                This is where all page content will be rendered
                The children prop contains the specific page components
              */}
              {children}
            </TooltipProvider>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
