import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Synarch",
  description: "AI company control surface"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
