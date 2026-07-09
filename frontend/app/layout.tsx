import type { Metadata } from "next";
import "./globals.css";
import { Instrument_Sans } from "next/font/google";
import { cn } from "@/lib/utils";
import { AppShell } from "@/components/app/AppShell";
import { TooltipProvider } from "@/components/ui/tooltip";

const instrumentSans = Instrument_Sans({
  subsets: ["latin", "latin-ext"],
  variable: "--font-sans",
});

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
    <html lang="tr" className={cn("font-sans", instrumentSans.variable)}>
      <body>
        <TooltipProvider>
          <AppShell>{children}</AppShell>
        </TooltipProvider>
      </body>
    </html>
  );
}
