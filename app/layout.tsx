import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PINAK Admin Dashboard",
  description: "Admin dashboard and command logger for PINAK-CLI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
