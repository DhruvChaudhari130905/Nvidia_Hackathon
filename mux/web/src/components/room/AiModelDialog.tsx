'use client';

import React, { useEffect, useState } from 'react';
import { X, Bot } from 'lucide-react';
import type { AiRole, RoomAi } from '@/types';
import { api, ApiError } from '@/lib/api';

interface AiModelDialogProps {
  isOpen: boolean;
  onClose: () => void;
  roomId: string;
  isOwner: boolean;
}

const ROLES: { role: AiRole; label: string; hint: string }[] = [
  { role: 'lightning', label: 'Coordinator', hint: 'fast; labels every message' },
  { role: 'super', label: 'Coder', hint: 'writes the code' },
  { role: 'ultra', label: 'Coder when stuck', hint: 'the strongest model' },
];

const PRESETS: Record<string, { label: string; base_url: string; models: Record<AiRole, string> }> = {
  token_factory: { label: 'Nebius Token Factory', base_url: 'https://api.tokenfactory.nebius.com/v1', models: { lightning: '', super: '', ultra: '' } },
  openai: { label: 'OpenAI', base_url: 'https://api.openai.com/v1', models: { lightning: '', super: '', ultra: '' } },
  anthropic: { label: 'Anthropic', base_url: 'https://api.anthropic.com/v1', models: { lightning: 'claude-haiku-4-5-20251001', super: 'claude-sonnet-5-5', ultra: 'claude-opus-5-5' } },
  openrouter: { label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1', models: { lightning: '', super: '', ultra: '' } },
  groq: { label: 'Groq', base_url: 'https://api.groq.com/openai/v1', models: { lightning: '', super: '', ultra: '' } },
  together: { label: 'Together', base_url: 'https://api.together.xyz/v1', models: { lightning: '', super: '', ultra: '' } },
  custom: { label: 'Custom (OpenAI-compatible)', base_url: '', models: { lightning: '', super: '', ultra: '' } },
};

const field = 'w-full bg-[var(--bg)] border border-[var(--line)] rounded px-3 py-2 text-sm';

function describe(ai: RoomAi): string {
  if (ai.source === 'room') return `This room's own key · ${PRESETS[ai.provider ?? '']?.label ?? ai.provider}`;
  if (ai.source === 'server') return "The MUX server's model";
  return 'No AI model, so the agents are off';
}

export function AiModelDialog({ isOpen, onClose, roomId, isOwner }: AiModelDialogProps) {
  const [ai, setAi] = useState<RoomAi | null>(null);
  const [provider, setProvider] = useState('openai');
  const [baseUrl, setBaseUrl] = useState(PRESETS.openai.base_url);
  const [apiKey, setApiKey] = useState('');
  const [models, setModels] = useState<Record<AiRole, string>>(PRESETS.openai.models);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [roleErrors, setRoleErrors] = useState<Partial<Record<AiRole, string>>>({});

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setRoleErrors({});
    api.getAi(roomId).then(view => {
      setAi(view);
      if (view.source === 'room' && view.provider && view.base_url && view.models) {
        setProvider(view.provider);
        setBaseUrl(view.base_url);
        setModels(view.models);
      }
    }).catch(e => setError(e instanceof Error ? e.message : 'Could not load the AI model'));
  }, [isOpen, roomId]);

  if (!isOpen) return null;

  const choosePreset = (name: string) => {
    setProvider(name);
    setBaseUrl(PRESETS[name].base_url);
    setModels(PRESETS[name].models);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setRoleErrors({});
    try {
      setAi(await api.setAi(roomId, { provider, base_url: baseUrl.trim(), api_key: apiKey.trim(), models }));
      setApiKey('');
    } catch (err) {
      // A failed model check comes back as {"errors": {role: text}}
      try {
        const detail = JSON.parse(err instanceof ApiError ? err.message : '');
        if (detail && typeof detail === 'object' && detail.errors) {
          setRoleErrors(detail.errors);
          setError('Nothing was saved: some models did not answer.');
          return;
        }
      } catch {
        // not JSON: a plain message
      }
      setError(err instanceof Error ? err.message : 'Could not save');
    } finally {
      setBusy(false);
    }
  };

  const useServer = async () => {
    setBusy(true);
    setError(null);
    try {
      setAi(await api.clearAi(roomId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not switch');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-[var(--panel)] rounded-xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="ai-title">
        <div className="flex items-center justify-between mb-2">
          <h2 id="ai-title" className="text-lg font-semibold flex items-center gap-2"><Bot className="w-5 h-5" /> AI model</h2>
          <button className="btn p-2" onClick={onClose} type="button" aria-label="Close"><X className="w-5 h-5" /></button>
        </div>
        {ai && <p className="mb-1 text-sm font-medium">{describe(ai)}</p>}
        {ai?.source === 'room' && ai.models && (
          <p className="mb-4 font-mono text-xs text-[var(--muted)]">
            {ROLES.map(r => `${r.label}: ${ai.models?.[r.role]}`).join(' · ')}
          </p>
        )}
        {!isOwner && <p className="mb-4 text-sm text-[var(--muted)]">Only the room&apos;s owner can change it.</p>}
        {error && <p className="mb-3 text-sm text-[var(--conflict)]" role="alert">{error}</p>}

        {isOwner && (
          <form onSubmit={save} className="space-y-3 p-4 bg-[var(--raised)] rounded-lg">
            <p className="text-sm text-[var(--muted)]">Use your own key: this room&apos;s agents run on it and you pay the provider.</p>
            <label className="block text-sm">Provider
              <select className={`${field} mt-1`} value={provider} onChange={e => choosePreset(e.target.value)}>
                {Object.entries(PRESETS).map(([name, p]) => <option key={name} value={name}>{p.label}</option>)}
              </select>
            </label>
            <label className="block text-sm">Base URL
              <input className={`${field} mt-1 font-mono`} value={baseUrl} onChange={e => setBaseUrl(e.target.value)} type="url" required placeholder="https://…/v1" />
            </label>
            <label className="block text-sm">API key
              <input className={`${field} mt-1`} value={apiKey} onChange={e => setApiKey(e.target.value)} type="password" autoComplete="off"
                required={ai?.source !== 'room'} placeholder={ai?.source === 'room' ? 'Leave empty to keep the saved key' : 'sk-…'} />
            </label>
            {ROLES.map(({ role, label, hint }) => (
              <label key={role} className="block text-sm">{label} <span className="text-[var(--muted)]">({hint})</span>
                <input className={`${field} mt-1 font-mono`} value={models[role]} required
                  onChange={e => setModels(m => ({ ...m, [role]: e.target.value.trim() }))} placeholder="model id" />
                {roleErrors[role] && <span className="mt-1 block text-xs text-[var(--conflict)]">{roleErrors[role]}</span>}
              </label>
            ))}
            <p className="text-xs text-[var(--muted)]">Saving sends one tiny request to each model to check the key and model ids.</p>
            <div className="flex flex-wrap gap-2">
              <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Checking…' : 'Save'}</button>
              {ai?.source === 'room' && (
                <button type="button" className="btn" onClick={useServer} disabled={busy}>Use the server&apos;s model</button>
              )}
            </div>
          </form>
        )}
        <div className="flex justify-end mt-4"><button className="btn" onClick={onClose} type="button">Done</button></div>
      </div>
    </div>
  );
}
