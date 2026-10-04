'use client';

import React, { useState } from 'react';
import { X, Copy, Mail, Link, UserPlus, UserCheck, UserX } from 'lucide-react';
import type { Room } from '@/types';
import { api } from '@/lib/api';

interface ShareDialogProps {
  isOpen: boolean;
  onClose: () => void;
  room: Room;
}

export function ShareDialog({ isOpen, onClose, room }: ShareDialogProps) {
  const [linkAccess, setLinkAccess] = useState(room.link_access);
  const [linkPermission, setLinkPermission] = useState<'editor' | 'viewer'>(room.link_permission === 'viewer' ? 'viewer' : 'editor');
  const [inviteEmail, setInviteEmail] = useState('');
  const [copied, setCopied] = useState(false);
  const [saving, setSaving] = useState(false);

  const shareUrl = `${window.location.origin}/room/${room.id}`;

  const handleCopyLink = async () => {
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSaveSharing = async () => {
    setSaving(true);
    try {
      await api.updateSharing(room.id, { link_access: linkAccess, link_permission: linkPermission });
      onClose();
    } catch (error) {
      console.error('Failed to update sharing:', error);
      alert('Failed to update sharing settings');
    } finally {
      setSaving(false);
    }
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setSaving(true);
    try {
      await api.updateSharing(room.id, {
        link_access: linkAccess,
        link_permission: linkPermission,
        invites: [inviteEmail],
      });
      setInviteEmail('');
    } catch (error) {
      console.error('Failed to invite:', error);
      alert('Failed to send invite');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-[var(--panel)] rounded-xl p-6 w-full max-w-md mx-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold">Share &ldquo;{room.title}&rdquo;</h2>
          <button className="btn p-2" onClick={onClose} type="button">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Link sharing */}
        <div className="space-y-4 mb-6 p-4 bg-[var(--raised)] rounded-lg">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Link access</p>
              <p className="text-sm text-[var(--muted)]">Control who can access via link</p>
            </div>
          </div>

          <div className="space-y-2">
            <label className="flex items-center gap-3 p-3 bg-[var(--bg)] rounded-lg border border-[var(--line)] cursor-pointer">
              <input
                type="radio"
                name="linkAccess"
                value="restricted"
                checked={linkAccess === 'restricted'}
                onChange={e => setLinkAccess(e.target.value as 'restricted' | 'anyone')}
                className="accent-[var(--coord)]"
              />
              <div>
                <p className="font-medium">Restricted</p>
                <p className="text-sm text-[var(--muted)]">Only invited people can access</p>
              </div>
            </label>
            <label className="flex items-center gap-3 p-3 bg-[var(--bg)] rounded-lg border border-[var(--line)] cursor-pointer">
              <input
                type="radio"
                name="linkAccess"
                value="anyone"
                checked={linkAccess === 'anyone'}
                onChange={e => setLinkAccess(e.target.value as 'restricted' | 'anyone')}
                className="accent-[var(--coord)]"
              />
              <div>
                <p className="font-medium">Anyone with the link</p>
                <p className="text-sm text-[var(--muted)]">Public link access</p>
              </div>
            </label>
          </div>

          {linkAccess === 'anyone' && (
            <div className="space-y-2 pt-2 border-t border-[var(--line)]">
              <p className="text-sm font-medium">Link permission</p>
              <label className="flex items-center gap-3 p-3 bg-[var(--bg)] rounded-lg border border-[var(--line)] cursor-pointer">
                <input
                  type="radio"
                  name="linkPermission"
                  value="editor"
                  checked={linkPermission === 'editor'}
                  onChange={e => setLinkPermission(e.target.value as 'editor' | 'viewer')}
                  className="accent-[var(--coord)]"
                />
                <div>
                  <p className="font-medium">Editor</p>
                  <p className="text-sm text-[var(--muted)]">Can steer, vote, edit code</p>
                </div>
              </label>
              <label className="flex items-center gap-3 p-3 bg-[var(--bg)] rounded-lg border border-[var(--line)] cursor-pointer">
                <input
                  type="radio"
                  name="linkPermission"
                  value="viewer"
                  checked={linkPermission === 'viewer'}
                  onChange={e => setLinkPermission(e.target.value as 'editor' | 'viewer')}
                  className="accent-[var(--coord)]"
                />
                <div>
                  <p className="font-medium">Viewer</p>
                  <p className="text-sm text-[var(--muted)]">Read-only access</p>
                </div>
              </label>
            </div>
          )}

          <div className="flex items-center gap-2 pt-2 border-t border-[var(--line)]">
            <input
              type="text"
              value={shareUrl}
              readOnly
              className="flex-1 bg-[var(--bg)] border border-[var(--line)] rounded px-3 py-2 text-sm font-mono"
            />
            <button
              className="btn"
              onClick={handleCopyLink}
              type="button"
            >
              {copied ? <UserCheck className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Invite by email */}
        <form onSubmit={handleInvite} className="space-y-4">
          <h3 className="font-medium">Invite by email</h3>
          <div className="flex gap-2">
            <input
              type="email"
              value={inviteEmail}
              onChange={e => setInviteEmail(e.target.value)}
              placeholder="teammate@example.com"
              className="flex-1 bg-[var(--bg)] border border-[var(--line)] rounded px-3 py-2"
            />
            <select
              value={linkPermission}
              onChange={e => setLinkPermission(e.target.value as 'editor' | 'viewer')}
              className="bg-[var(--bg)] border border-[var(--line)] rounded px-3 py-2"
            >
              <option value="editor">Editor</option>
              <option value="viewer">Viewer</option>
            </select>
            <button type="submit" className="btn primary" disabled={saving || !inviteEmail}>
              <UserPlus className="w-4 h-4" />
            </button>
          </div>
        </form>

        {/* Current members */}
        <div className="mt-6 pt-4 border-t border-[var(--line)]">
          <h3 className="font-medium mb-3">Current members</h3>
          <div className="space-y-2 max-h-40 overflow-y-auto">
            {room.members.map(member => (
              <div key={member.user_id} className="flex items-center justify-between p-2 bg-[var(--raised)] rounded">
                <div className="flex items-center gap-3">
                  <span className="av" style={{ background: member.user.color }}>
                    {member.user.initials}
                  </span>
                  <div>
                    <p className="font-medium">{member.user.name}</p>
                    <p className="text-sm text-[var(--muted)] capitalize">{member.permission}</p>
                  </div>
                </div>
                <span className="text-xs text-[var(--muted)] uppercase">{member.domain_role}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button className="btn" onClick={onClose} type="button" disabled={saving}>
            Cancel
          </button>
          <button className="btn primary" onClick={handleSaveSharing} type="button" disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}