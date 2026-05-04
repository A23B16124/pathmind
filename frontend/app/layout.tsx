import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { RegisterSW } from '@/components/pwa/RegisterSW'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'PathMind',
  description: 'Multi-slide agentic pathology co-pilot',
  manifest: '/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    title: 'PathMind',
    statusBarStyle: 'black-translucent',
  },
  icons: {
    icon: [
      { url: '/icons/favicon-32.png', sizes: '32x32', type: 'image/png' },
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
    ],
    apple: '/icons/apple-touch-icon.png',
  },
}

export const viewport: Viewport = {
  themeColor: '#05080F',
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className="dark">
      <body className={inter.className}>
        {children}
        <RegisterSW />
      </body>
    </html>
  )
}
