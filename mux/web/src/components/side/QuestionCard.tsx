'use client';

import React, { useState } from 'react';
import type { Question } from '@/types';
import { formatCountdown, useSecondsUntil } from '@/lib/countdown';

interface QuestionCardProps {
  question: Question;
  currentUserRole: 'owner' | 'editor' | 'viewer';
  onAnswer: (questionId: string, answer: string) => void;
}

export function QuestionCard({ question, currentUserRole, onAnswer }: QuestionCardProps) {
  const isOpen = question.status === 'open';
  const timeLeft = useSecondsUntil(question.expires_at, isOpen);
  // The answer we sent, until the server's question.answered event closes the card
  const [sentAnswer, setSentAnswer] = useState<string | null>(null);

  const canAnswer = isOpen && !sentAnswer && timeLeft > 0 && currentUserRole !== 'viewer';

  const handleAnswer = (answer: string) => {
    if (!canAnswer) return;
    onAnswer(question.id, answer);
    setSentAnswer(answer);
  };

  let resolved: string | null = null;
  if (question.status === 'answered') resolved = `Answered: ${question.answer}. Sent to the coder as a merge.`;
  else if (question.status === 'defaulted') resolved = `No answer in time, so the default was used: ${question.answer ?? question.default_option}.`;
  else if (sentAnswer) resolved = `Answer sent: ${sentAnswer}.`;
  else if (timeLeft === 0) resolved = `Time's up. The coder will use the default (${question.default_option}).`;

  return (
    <div className="card ask">
      <div className="card-head">
        <span className="card-kind">Agent question · task {question.task_id}</span>
        {isOpen && <span className="timer mono">{formatCountdown(timeLeft)}</span>}
      </div>
      <h4>{question.text}</h4>
      <p className="why">{question.default_option ? `Default: ${question.default_option}` : ''}</p>

      {resolved ? (
        <div className="resolved">{resolved}</div>
      ) : (
        <div className="opts">
          {question.options.map(option => (
            <button
              key={option}
              className="opt"
              onClick={() => handleAnswer(option)}
              disabled={!canAnswer}
              data-ans={option}
              type="button"
            >
              <span className="lbl">{option}</span>
              {option === question.default_option && <span className="n mono">default</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
