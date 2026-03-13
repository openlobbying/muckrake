import { Calendar, Users, Banknote, FileText, Megaphone, MessageCircle, PoundSterling, Mic, MicVocal, Drama, Handshake, Briefcase, Building, UserCheck, MapPin, Plane, Gift, Home, TrendingUp, Info } from '@lucide/svelte';

export interface TypeInfo {
  key: string;
  label?: string;
  markerColor: string;
  badgeBg: string;
  icon: any;
}

const TYPES: Record<string, TypeInfo> = {
  Payment: { 
    key: 'Payment', 
    label: 'Payment', 
    markerColor: '#3b82f6', 
    badgeBg: '#eff6ff', 
    icon: PoundSterling 
  },
  Representation: { 
    key: 'Representation', 
    label: 'Representation', 
    markerColor: '#10b981', 
    badgeBg: '#ecfdf5', 
    icon: Drama 
  },
  Membership: { 
    key: 'Membership', 
    label: 'Membership', 
    markerColor: '#f59e0b', 
    badgeBg: '#fffbeb', 
    icon: Users 
  },
  Employment: {
    key: 'Employment',
    label: 'Employment',
    markerColor: '#0891b2',
    badgeBg: '#ecfeff',
    icon: Briefcase
  },
  Directorship: {
    key: 'Directorship',
    label: 'Directorship',
    markerColor: '#7c3aed',
    badgeBg: '#f5f3ff',
    icon: Building
  },
  Family: {
    key: 'Family',
    label: 'Family',
    markerColor: '#ec4899',
    badgeBg: '#fdf2f8',
    icon: UserCheck
  },
  Ownership: {
    key: 'Ownership',
    label: 'Ownership',
    markerColor: '#f97316',
    badgeBg: '#fff7ed',
    icon: TrendingUp
  },
  Visit: {
    key: 'Visit',
    label: 'Visit',
    markerColor: '#06b6d4',
    badgeBg: '#f0fdfa',
    icon: Plane
  },
  Trip: {
    key: 'Trip',
    label: 'Trip',
    markerColor: '#06b6d4',
    badgeBg: '#f0fdfa',
    icon: Plane
  },
  Gift: {
    key: 'Gift',
    label: 'Gift',
    markerColor: '#f59e0b',
    badgeBg: '#fffbeb',
    icon: Gift
  },
  Donation: {
    key: 'Donation',
    label: 'Donation',
    markerColor: '#8b5cf6',
    badgeBg: '#faf5ff',
    icon: Banknote
  },
  Property: {
    key: 'Property',
    label: 'Property',
    markerColor: '#16a34a',
    badgeBg: '#f0fdf4',
    icon: Home
  },
  Meeting: {
    key: 'Meeting',
    label: 'Meeting',
    markerColor: '#0ea5e9',
    badgeBg: '#f0f9ff',
    icon: Handshake
  },
  Event: { 
    key: 'Event', 
    label: 'Event', 
    markerColor: '#8b5cf6', 
    badgeBg: '#f5f3ff', 
    icon: MessageCircle 
  },
  Evidence: {
    key: 'Evidence',
    label: 'Evidence',
    markerColor: '#ef4444',
    badgeBg: '#fef2f2',
    icon: MicVocal
  },
  PublicDisclosure: {
    key: 'PublicDisclosure',
    label: 'Disclosure',
    markerColor: '#6b7280',
    badgeBg: '#f3f4f6',
    icon: FileText
  },
  UnknownLink: {
    key: 'UnknownLink',
    label: 'Other Interest',
    markerColor: '#6b7280',
    badgeBg: '#f9fafb',
    icon: Info
  }
};

export function getTypeInfo(schema?: string): TypeInfo {
  if (!schema || !TYPES[schema]) {
    return { 
      key: schema || 'Unknown', 
      markerColor: '#6b7280', 
      badgeBg: '#f3f4f6', 
      icon: Calendar 
    };
  }
  return TYPES[schema];
}

export function allTypes(): TypeInfo[] {
  return Object.values(TYPES);
}
