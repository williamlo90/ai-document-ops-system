import { useSearchParams } from 'react-router-dom'
import { ExceptionsPage } from './ExceptionsPage'
import { ReviewQueuePage } from './ReviewQueuePage'

export function InboxPage() {
  const [params] = useSearchParams()
  return params.get('state') === 'blocked' ? <ExceptionsPage /> : <ReviewQueuePage />
}
