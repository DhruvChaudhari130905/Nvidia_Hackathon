'use client';

import React from 'react';
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from 'lucide-react';

// The thin strip a collapsed side column leaves behind; clicking it brings the column back
export function PanelRail({ side, label, badge, onOpen }: { side: 'left' | 'right'; label: string; badge?: number; onOpen: () => void }) {
  const Icon = side === 'left' ? PanelLeftOpen : PanelRightOpen;
  return (
    <button className={`col panel-rail ${side}`} onClick={onOpen} type="button" aria-expanded={false} aria-label={`Show ${label}`} title={`Show ${label}`}>
      <Icon className="h-4 w-4" />
      <span className="panel-rail-label">{label}</span>
      {!!badge && <span className="panel-rail-badge">{badge}</span>}
    </button>
  );
}

// The collapse button in a column's header
export function CollapseButton({ side, label, onCollapse }: { side: 'left' | 'right'; label: string; onCollapse: () => void }) {
  const Icon = side === 'left' ? PanelLeftClose : PanelRightClose;
  return (
    <button className="panel-collapse" onClick={onCollapse} type="button" aria-expanded aria-label={`Hide ${label}`} title={`Hide ${label}`}>
      <Icon className="h-3.5 w-3.5" />
    </button>
  );
}
