import { useEffect, useState } from 'react'
import { Shield, RefreshCw } from 'lucide-react'
import { api } from '../services/api'
import type { BlockchainAuditRecord, BlockchainNetworkStatus } from '../types'
import './BlockchainAuditCard.css'

export function BlockchainAuditCard({ caseId, decisionTimestamp }: { caseId: string; decisionTimestamp?: string }) {
  const [records, setRecords] = useState<BlockchainAuditRecord[]>([])
  const [network, setNetwork] = useState<BlockchainNetworkStatus | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempts = 0
    const refresh = async () => {
      try {
        const [status, audits] = await Promise.all([api.getBlockchainStatus(), api.getAudits(caseId)])
        if (cancelled) return
        setNetwork(status); setRecords(audits.records)
        if ((audits.records.some(r => r.status === 'PENDING') || (status.enabled && !audits.records.length)) && attempts++ < 10) {
          timer = setTimeout(() => void refresh(), 2000)
        }
      } catch {
        if (!cancelled) setMessage('Audit information unavailable. Screening remains saved locally.')
      }
    }
    void refresh()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [caseId, decisionTimestamp])

  const act = async (record?: BlockchainAuditRecord, verify = false) => {
    setBusy(true); setMessage('')
    try {
      const result = verify && record
        ? await api.verifyAudit(caseId, record.record_type, record.version)
        : await api.anchorAudit(caseId, record?.record_type, record?.version)
      setMessage(result.error_message || (result.status === 'VERIFIED' && result.digest_match === true
        ? 'Digest matches the immutable audit record at the last verification.' : result.status.replaceAll('_', ' ')))
      const [status, audits] = await Promise.all([api.getBlockchainStatus(), api.getAudits(caseId)])
      setNetwork(status); setRecords(audits.records)
    } catch { setMessage('Audit operation unavailable. Screening remains saved locally.') }
    finally { setBusy(false) }
  }
  return <section className="result-card blockchain-card">
    <div className="card-header"><Shield size={20} className="card-icon" /><div>
      <h3>Blockchain Audit / Record Integrity</h3>
      <p className="card-subtitle">Cryptographic evidence of saved results. This does not verify identity authenticity.</p>
    </div></div>
    <p>Network: {network?.chain_id === 31337 ? 'Local Hardhat' : 'Configured EVM network'} · Chain ID: {network?.chain_id ?? '—'}</p>
    {network && !network.enabled && <p>Audit anchoring is disabled. Screening remains available locally.</p>}
    {network?.enabled && (!network.rpc_reachable || !network.contract_reachable) &&
      <p className="audit-warning">CHAIN UNAVAILABLE / CONTRACT UNAVAILABLE — screening remains saved locally. Anchoring can be retried.</p>}
    {records.map(record => <div key={record.id} className={`audit-record ${record.status === 'TAMPER_DETECTED' ? 'audit-integrity-failure' : ''}`}>
      <strong>{record.record_type.replaceAll('_', ' ')} v{record.version}</strong>
      <p className="audit-status">{record.status === 'TAMPER_DETECTED' ? '⚠ INTEGRITY FAILURE' : record.status.replaceAll('_', ' ')}</p>
      {record.status === 'TAMPER_DETECTED' && <p>The locally saved record no longer matches its immutable audit proof.</p>}
      {record.status === 'VERIFIED' && <p>Digest matched at {record.last_verified_at ? new Date(record.last_verified_at).toLocaleString() : 'last verification'}. Verify again to check current data.</p>}
      <dl><dt>Transaction</dt><dd>{record.transaction_hash || 'Not mined'}</dd>
        <dt>Block</dt><dd>{record.block_number ?? '—'}</dd>
        <dt>Contract</dt><dd>{record.contract_address || 'Not configured'}</dd>
        <dt>Anchored</dt><dd>{record.anchored_at ? new Date(record.anchored_at).toLocaleString() : '—'}</dd></dl>
      {record.error_message && <p>{record.error_message}</p>}
      <div className="audit-actions">
        <button className="btn-secondary" disabled={busy || !network?.enabled} onClick={() => void act(record, true)}>Verify Integrity</button>
        {['PENDING', 'NOT_ANCHORED', 'CHAIN_UNAVAILABLE', 'FAILED'].includes(record.status) &&
          <button className="btn-secondary" disabled={busy || !network?.enabled} onClick={() => void act(record)}>Retry Anchoring</button>}
      </div>
    </div>)}
    {network?.enabled && !records.length && <button className="btn-secondary" disabled={busy} onClick={() => void act()}>Anchor Saved Screening</button>}
    {busy && <p><RefreshCw size={14} /> Checking audit chain…</p>}
    {message && <p role="status">{message}</p>}
  </section>
}
