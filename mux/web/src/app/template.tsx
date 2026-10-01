// Re-mounts on every navigation, so each page fades in
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="page-in flex min-h-full flex-1 flex-col">{children}</div>;
}
