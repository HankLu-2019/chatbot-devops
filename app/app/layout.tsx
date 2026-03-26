import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Acme Engineering Assistant",
  description: "RAG-powered internal knowledge chatbot for Acme Engineering",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  );
}
