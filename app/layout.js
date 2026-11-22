import { Manrope, Barlow_Condensed } from 'next/font/google'
import Providers from './Providers'
import "./globals.css";
import Navbar from './components/Navbar'
import Sidebar from './components/Sidebar'
import UpgradeModal from './components/UpgradeModal'

const manrope = Manrope({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-ui'
})

const barlowCondensed = Barlow_Condensed({
  subsets: ['latin'],
  weight: ['500', '600', '700'],
  variable: '--font-figure'
})

export const metadata = {
  title: 'FinnWinn — Autonomous Equity & Market Intelligence',
  description: 'Multi-agent financial intelligence and real-time portfolio risk analysis.',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${manrope.variable} ${barlowCondensed.variable}`}>
      <body>
        <Providers>
          <Navbar />
          <UpgradeModal />
          <div style={{ display: 'flex', minHeight: 'calc(100vh - 60px)' }}>
            <Sidebar />
            <div style={{ flex: 1, minWidth: 0, overflow: 'auto' }}>
              {children}
            </div>
          </div>
        </Providers>
      </body>
    </html>
  )
}
