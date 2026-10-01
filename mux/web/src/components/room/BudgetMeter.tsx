'use client';

import React from 'react';

interface BudgetMeterProps {
  tokensUsed: number;
  tokensCap: number;
  runsUsed: number;
  runsCap: number;
}

export function BudgetMeter({ tokensUsed, tokensCap, runsUsed, runsCap }: BudgetMeterProps) {
  const tokenPercent = Math.min(100, (tokensUsed / tokensCap) * 100);
  const tokenColor = tokenPercent > 90 ? 'var(--conflict)' : tokenPercent > 70 ? 'var(--ask)' : 'var(--coord)';

  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  return (
    <div className="budget" title="Room budget">
      <div className="row">
        <span>{formatNumber(tokensUsed)} / {formatNumber(tokensCap)} tokens</span>
        <span>{runsUsed} / {runsCap} builds</span>
      </div>
      <div className="bar">
        <i style={{ width: `${tokenPercent}%`, background: tokenColor }} />
      </div>
    </div>
  );
}