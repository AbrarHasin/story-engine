import { useState } from 'react'
import ConfigPanel from '@/components/ConfigPanel'
import GenerationView from '@/components/GenerationView'
import { useGenerate, type GenerateRequest } from '@/hooks/useGenerate'

export default function GeneratePage() {
  const { generate, status, ...genState } = useGenerate()
  const [lastRequest, setLastRequest] = useState<GenerateRequest | null>(null)

  const handleSubmit = async (req: GenerateRequest) => {
    setLastRequest(req)
    await generate(req)
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6 items-start">
      <ConfigPanel
        onSubmit={handleSubmit}
        isRunning={status === 'running'}
      />
      {(status !== 'idle' || lastRequest) && (
        <GenerationView status={status} genState={genState} request={lastRequest} />
      )}
      {status === 'idle' && !lastRequest && (
        <div className="hidden lg:flex flex-col items-center justify-center h-96 text-slate-600 gap-3">
          <div className="text-6xl">✦</div>
          <p className="text-lg">Configure your story and hit Generate</p>
        </div>
      )}
    </div>
  )
}
