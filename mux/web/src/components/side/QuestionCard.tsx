'use client';

import React, { useState, useEffect } from 'react';
import type { Question, User } from '@/types';
import { api } from '@/lib/api';
import { format } from 'date-fns';

interface QuestionCardProps {
  question: Question;
  currentUser: User;
  currentUserRole: 'owner' | 'editor' | 'viewer';
  onAnswer: (questionId: string, answer: string) => void;
}

export function QuestionCard({ question, currentUser, currentUserRole, onAnswer }: QuestionCardProps) {
  const [timeLeft, setTimeLeft] = useState(300); // 5 minutes
  const [answered, setAnswered] = useState(false);

  useEffect(() => {
    const expiresAt = new Date(question.expires_at).getTime();
    const now = Date.now();
    setTimeLeft(Math.max(0, Math.floor((expiresAt - now) / 1000)));

    const interval = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          setAnswered(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [question.expires_at]);

  const handleAnswer = (answer: string) => {
    if (answered || currentUserRole === 'viewer') return;
    onAnswer(question.id, answer);
    setAnswered(true);
  };

  return (
    <div className="card ask">
      <div className="card-head">
        <span className="card-kind">Agent question · task {question.task_id}</span>
        <span className="timer mono">{format(new Date(0).setSeconds(timeLeft), 'm:ss')}</span>
      </div>
      <h4>{question.text}</h4>
      <p className="why">{question.default_option ? `Default: ${question.default_option}` : ''}</p>

      {!answered ? (
        <div className="opts">
          {question.options.map((option, index) => (
            <button
              key={option}
              className="opt"
              onClick={() => handleAnswer(option)}
              aria-pressed={false}
              disabled={answered || currentUserRole === 'viewer'}
              data-ans={option}
            >
              <span className="lbl">{option}</span>
              {option === question.default_option && <span className="n mono">default</span>}
            </button>
          ))}
        </div>
      ) : (
        <div className="resolved">
          Answer sent to the coder as a merge.
        </div>
      )}
    </div>
  );
}