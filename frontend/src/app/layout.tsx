import type { Metadata } from "next";
import Script from "next/script";
import localFont from "next/font/local";
import "./globals.css";
import { DatadogInit } from "@/components/DatadogInit";
import { NEW_RELIC_AGENT_URL, getNewRelicScript, isNewRelicEnabled } from "@/lib/newrelic-config";
import { TolgeeClientProvider } from "@/components/TolgeeClientProvider";
import { AuthProvider } from "@/context/AuthContext";
import { GDPRConsentProvider } from "@/context/GDPRConsentContext";
import { DemoProviderWrapper } from "@/components/DemoProviderWrapper";
import { AppShell } from "@/components/shell";

// Font files are committed locally so production and CI builds require no
// external Google Fonts access. These variables are consumed by
// --stitch-font-sans / --stitch-font-mono in tokens.css.
// preload: false — the sans/mono stacks prefer system fonts first, so these
// are fallbacks; preloading them would delay the (text) LCP element while it
// waits on the webfont. display: swap paints with the system fallback first.
const inter = localFont({
  src: "../assets/fonts/InterVariable.woff2",
  variable: "--font-inter",
  display: "swap",
  preload: false,
  weight: "100 900",
  style: "normal",
});
const jetbrainsMono = localFont({
  src: "../assets/fonts/JetBrainsMonoVariable.woff2",
  variable: "--font-jetbrains-mono",
  display: "swap",
  preload: false,
  weight: "100 800",
  style: "normal",
});

export const metadata: Metadata = {
  title: "justippo",
  description:
    "Search, translate, and exchange cross-border documents across EU languages with formatting preserved.",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "32x32" },
      { url: "/favicon.png", type: "image/png", sizes: "64x64" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  openGraph: {
    title: "justippo",
    description:
      "Search, translate, and exchange cross-border documents across EU languages with formatting preserved.",
    images: ["https://justippo.tech/opengraph-image.jpg"],
  },
  twitter: {
    card: "summary_large_image",
    title: "justippo",
    description:
      "Search, translate, and exchange cross-border documents across EU languages with formatting preserved.",
    images: ["https://justippo.tech/opengraph-image.jpg"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var s=JSON.parse(localStorage.getItem("evidenceeu_settings")||"{}");var t=s.theme||"system";var d=t==="dark"||(t==="system"&&matchMedia("(prefers-color-scheme:dark)").matches);if(d)document.documentElement.classList.add("dark")}catch(e){}`,
          }}
        />
      </head>
      <body className="min-h-screen bg-surface font-sans antialiased">
        <TolgeeClientProvider>
          <AuthProvider>
            <GDPRConsentProvider>
              <DemoProviderWrapper>
                <AppShell>{children}</AppShell>
              </DemoProviderWrapper>
            </GDPRConsentProvider>
          </AuthProvider>
          <DatadogInit />
        </TolgeeClientProvider>
        {/*
         * New Relic browser agent — deferred to afterInteractive so the RUM
         * loader no longer render-blocks FCP/LCP (it previously fetched before
         * CSS in <head>). Trade-off: RUM initialises slightly later; Core Web
         * Vitals are still captured via buffered PerformanceObserver entries,
         * and Datadog RUM remains the primary NFR-09 source.
         */}
        {isNewRelicEnabled() && (
          <>
            <Script
              id="newrelic-inline"
              strategy="afterInteractive"
              dangerouslySetInnerHTML={{ __html: getNewRelicScript() }}
            />
            <Script id="newrelic-agent" strategy="afterInteractive" src={NEW_RELIC_AGENT_URL} />
          </>
        )}
      </body>
    </html>
  );
}
