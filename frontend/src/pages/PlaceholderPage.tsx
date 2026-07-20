import { Construction } from 'lucide-react'
import { PageHeader, Panel } from '../shared/ui'

export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return <div className="ops-page"><PageHeader title={title} description={description} /><Panel><div className="ops-state"><Construction size={28} /><strong>{title} is being upgraded</strong><span>The verified workflow remains available while this page is converted to the approved design.</span></div></Panel></div>
}
