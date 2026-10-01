'use client';

import React from 'react';
import type { MessageLabel } from '@/types';

interface LabelChipProps {
  label: MessageLabel;
}

const labelStyles: Record<MessageLabel, string> = {
  merge: 'chip merge',
  queue: 'chip queue',
  interrupt: 'chip interrupt',
  conflict: 'chip conflict',
  chat: 'chip chat',
};

const labelLabels: Record<MessageLabel, string> = {
  merge: 'merge',
  queue: 'queue',
  interrupt: 'interrupt',
  conflict: 'conflict',
  chat: 'chat',
};

export function LabelChip({ label }: LabelChipProps) {
  return <span className={labelStyles[label]}>{labelLabels[label]}</span>;
}