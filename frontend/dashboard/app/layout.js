import './globals.css';

export const metadata = {
  title: 'Cluster Dashboard',
  description: 'Real-time cluster monitoring dashboard',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="bg-slate-900 text-slate-100">{children}</body>
    </html>
  );
}
