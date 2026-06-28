import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tandela Review",
  description: "Dental documentation review workspace",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
