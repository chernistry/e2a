import { redirect } from 'next/navigation';

export default async function Dashboard() {
  // For now, redirect to overview - later we can add auth check
  redirect('/dashboard/overview');
}
