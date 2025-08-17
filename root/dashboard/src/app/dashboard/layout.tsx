import AppSidebar from '@/components/layout/app-sidebar';
import Header from '@/components/layout/header';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import type { Metadata } from 'next';
import { cookies } from 'next/headers';

export const metadata: Metadata = {
  title: 'Octup E²A Dashboard',
  description: 'SLA Radar + Invoice Guard with AI Exception Analyst'
};

export default async function DashboardLayout({
  children
}: {
  children: React.ReactNode;
}) {
  // Persisting the sidebar state in the cookie.
  const cookieStore = await cookies();
  const defaultOpen = cookieStore.get("sidebar_state")?.value === "true"
  return (
    <div className="h-full">
      <SidebarProvider defaultOpen={defaultOpen}>
        <AppSidebar />
        <SidebarInset className="h-full overflow-y-auto">
          <Header />
          {/* page content */}
          <div className="p-4 md:p-8 pt-6 max-w-7xl mx-auto w-full">
            {children}
          </div>
          {/* page content ends */}
        </SidebarInset>
      </SidebarProvider>
    </div>
  );
}
