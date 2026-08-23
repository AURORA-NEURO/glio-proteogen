import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GLIO Proteogen Control Room",
  description: "Operational workspace for GLIO Proteogen model routes.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
