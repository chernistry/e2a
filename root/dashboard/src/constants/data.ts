import { NavItem } from '@/types';

export type Product = {
  photo_url: string;
  name: string;
  description: string;
  created_at: string;
  price: number;
  id: number;
  category: string;
  updated_at: string;
};

//Info: The following data is used for the sidebar navigation and Cmd K bar.
export const navItems: NavItem[] = [
  {
    title: 'Dashboard',
    url: '/dashboard/overview',
    icon: 'dashboard',
    isActive: false,
    shortcut: ['d', 'd'],
    items: [] // Empty array as there are no child items for Dashboard
  },
  {
    title: 'Product',
    url: '/dashboard/product',
    icon: 'product',
    shortcut: ['p', 'p'],
    isActive: false,
    items: [] // No child items
  },
  {
    title: 'Account',
    url: '#', // Placeholder as there is no direct link for the parent
    icon: 'billing',
    isActive: true,

    items: [
      {
        title: 'Profile',
        url: '/dashboard/profile',
        icon: 'userPen',
        shortcut: ['m', 'm']
      },
      {
        title: 'Login',
        shortcut: ['l', 'l'],
        url: '/',
        icon: 'login'
      }
    ]
  },
  {
    title: 'Kanban',
    url: '/dashboard/kanban',
    icon: 'kanban',
    shortcut: ['k', 'k'],
    isActive: false,
    items: [] // No child items
  }
];

export interface SaleUser {
  id: number;
  name: string;
  email: string;
  amount: string;
  image: string;
  initials: string;
}

export const recentSalesData: SaleUser[] = [
  {
    id: 1,
    name: 'Maria Silva',
    email: 'maria.silva@gmail.com',
    amount: '+$1,847.50',
    image: 'https://api.slingacademy.com/public/sample-users/1.png',
    initials: 'MS'
  },
  {
    id: 2,
    name: 'Carlos Santos',
    email: 'carlos.santos@hotmail.com',
    amount: '+$67.25',
    image: 'https://api.slingacademy.com/public/sample-users/2.png',
    initials: 'CS'
  },
  {
    id: 3,
    name: 'Ana Ferreira',
    email: 'ana.ferreira@yahoo.com.br',
    amount: '+$234.80',
    image: 'https://api.slingacademy.com/public/sample-users/3.png',
    initials: 'AF'
  },
  {
    id: 4,
    name: 'Pedro Oliveira',
    email: 'pedro.oliveira@outlook.com',
    amount: '+$156.90',
    image: 'https://api.slingacademy.com/public/sample-users/4.png',
    initials: 'PO'
  },
  {
    id: 5,
    name: 'Lucia Costa',
    email: 'lucia.costa@uol.com.br',
    amount: '+$89.45',
    image: 'https://api.slingacademy.com/public/sample-users/5.png',
    initials: 'LC'
  }
];
