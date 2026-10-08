const paths: Record<string, string> = {
  '/': 'M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1z',
  '/transactions': 'M8 7h12M8 12h12M8 17h12M4 7h.01M4 12h.01M4 17h.01',
  '/recurring': 'M4 12a7 7 0 0 1 12-4.9L18 9M20 12a7 7 0 0 1-12 4.9L6 15M18 4.5V9h-4.5M6 19.5V15h4.5',
  '/bills': 'M4 10h16M8.5 3.5v4M15.5 3.5v4M6 5.5h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-10a2 2 0 0 1 2-2z',
  '/budgets': 'M12 4a8 8 0 1 0 8 8h-8zM15 3.6A8 8 0 0 1 20.4 9H15z',
  '/networth': 'M4 19.5h16M6 16l4-5 3.5 3 5-7',
  '/goals': 'M6 21V4M6 4.5h11l-2.5 4 2.5 4H6',
  '/accounts': 'M3.5 9 12 4.5 20.5 9M5 9.5v8M9.7 9.5v8M14.3 9.5v8M19 9.5v8M3.5 20h17',
  '/proposals': 'M7 4h10v3H7zM7 5H5v16h14V5h-2M8 12l2 2 5-5M8 18h8',
  '/rules': 'M4 6h16M8 4v4M4 12h16M16 10v4M4 18h16M10 16v4',
  '/settings': 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6M12 3.5v2.2M12 18.3v2.2M20.5 12h-2.2M5.7 12H3.5M18 6l-1.6 1.6M7.6 16.4 6 18M18 18l-1.6-1.6M7.6 7.6 6 6',
}
export default function NavIcon({ path }: { path: string }) {
  return <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={paths[path]} /></svg>
}
