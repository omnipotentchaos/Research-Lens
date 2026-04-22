import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "ResearchLens — AI Research Intelligence",
  description: "Automatically retrieve, cluster, and analyze academic papers to map any research field in minutes.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="bg-[#080b14] text-slate-100 antialiased min-h-screen">
        {children}
      </body>
    </html>
  );
}
