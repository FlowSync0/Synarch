import "./globals.css";
import "@fontsource-variable/inter";
import type { Metadata } from "next";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Synarch",
  description: "AI company control surface"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
