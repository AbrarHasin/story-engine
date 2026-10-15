import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const API = import.meta.env.VITE_API_BASE_URL || ''

export interface Personality {
  id: string
  name: string
  voice?: string
  tone?: string
  reading_level?: string
  banned_words: string[]
  locale: string
  is_default: boolean
}

async function fetchPersonalities(): Promise<Personality[]> {
  const r = await fetch(`${API}/api/v1/personalities/`)
  if (!r.ok) throw new Error('Failed to fetch personalities')
  return r.json()
}

async function createPersonality(body: Omit<Personality, 'id'>): Promise<Personality> {
  const r = await fetch(`${API}/api/v1/personalities/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error('Failed to create personality')
  return r.json()
}

async function deletePersonality(id: string): Promise<void> {
  await fetch(`${API}/api/v1/personalities/${id}`, { method: 'DELETE' })
}

export function usePersonalities() {
  return useQuery({ queryKey: ['personalities'], queryFn: fetchPersonalities })
}

export function useCreatePersonality() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createPersonality,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['personalities'] }),
  })
}

export function useDeletePersonality() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deletePersonality,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['personalities'] }),
  })
}
