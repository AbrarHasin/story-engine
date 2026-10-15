/**
 * useGenerate — opens an SSE connection to POST /api/v1/stories/generate
 * and feeds events into the Zustand generation store.
 *
 * SSE via fetch (not EventSource) so we can POST with a body.
 */
import { useGenerationStore } from '@/stores/generationStore'

export interface GenerateRequest {
  topic: string
  tonality: string
  audience: string
  length: string
  locale: string
  personality_id?: string | null
  include_light: boolean
  include_dark: boolean
  include_facts: boolean
}

const API = import.meta.env.VITE_API_BASE_URL || ''

export function useGenerate() {
  const store = useGenerationStore()

  const generate = async (req: GenerateRequest) => {
    store.reset()

    let resp: Response
    try {
      resp = await fetch(`${API}/api/v1/stories/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(req),
      })
    } catch (err) {
      store.setError(`Network error: ${err instanceof Error ? err.message : 'could not reach backend'}`)
      return
    }

    if (!resp.ok || !resp.body) {
      const text = await resp.text().catch(() => resp.statusText)
      store.setError(`HTTP ${resp.status}: ${text}`)
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        let eventType = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            let data: any
            try {
              data = JSON.parse(line.slice(6))
            } catch {
              console.warn('[SSE] Malformed JSON:', line.slice(6))
              continue
            }

            switch (eventType) {
              case 'start':
                store.start(data.story_id, data.run_id)
                break
              case 'node_complete':
                store.nodeComplete(data)
                break
              case 'done':
                store.finish(data.tokens, data.langfuse_trace)
                break
              case 'error':
                store.setError(data.message)
                break
            }
            eventType = ''
          }
        }
      }
    } catch (err) {
      if (store.status === 'running') {
        store.setError(`Stream interrupted: ${err instanceof Error ? err.message : 'unknown error'}`)
      }
    }
  }

  return { generate, ...store }
}
