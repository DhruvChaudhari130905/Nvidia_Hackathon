// Turns live room events into notifications (see notifications.ts)
import type { AppEvent, PlanItem, User } from '@/types';
import { notify } from './notifications';

export interface RoomNotifyContext {
  roomTitle: string;
  currentUser: User;
  nameOf: (userId: string) => string;
  planItem: (id: string) => PlanItem | undefined;
  focusSidePanel?: () => void;
}

const clip = (text: string, n = 140) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);

function mentions(text: string, user: User): boolean {
  const handles = [user.name, user.name.split(' ')[0], user.email.split('@')[0]].filter(Boolean).map(h => h.toLowerCase());
  const lower = text.toLowerCase();
  return lower.includes('@everyone') || lower.includes('@here') || handles.some(h => lower.includes(`@${h}`));
}

export function notifyForEvent(event: AppEvent, ctx: RoomNotifyContext) {
  const { currentUser, roomTitle } = ctx;

  switch (event.type) {
    case 'message.posted': {
      const msg = event.payload;
      if (msg.user_id === currentUser.id) return; // your own message
      const who = ctx.nameOf(msg.user_id);
      if (mentions(msg.text, currentUser)) {
        notify({ category: 'mentions', title: `${who} mentioned you in ${roomTitle}`, body: clip(msg.text) });
      } else {
        notify({ category: 'messages', title: `${who} · ${roomTitle}`, body: clip(msg.text) });
      }
      return;
    }

    case 'plan.item_updated': {
      const status = event.payload.changes.status;
      if (status !== 'done' && status !== 'skipped_conflict' && status !== 'skipped_question') return;
      const changed = event.payload.changes as { title?: string };
      const title = changed.title ?? ctx.planItem(event.payload.id)?.title ?? 'A task';
      notify(
        status === 'done'
          ? { category: 'tasks', tone: 'ok', title: 'Task completed', body: title }
          : { category: 'tasks', tone: 'err', title: 'Task skipped', body: `${title} · waiting on a ${status === 'skipped_conflict' ? 'vote' : 'answer'}` },
      );
      return;
    }

    case 'build.result': {
      const { passed, errors = [] } = event.payload;
      notify(
        passed
          ? { category: 'builds', tone: 'ok', title: 'Build passed', body: roomTitle }
          : { category: 'builds', tone: 'err', title: 'Build failed', body: errors[0] ? clip(errors[0]) : `${errors.length} errors` },
      );
      return;
    }

    case 'question.opened':
      notify({ category: 'decisions', title: 'The agent has a question', body: clip(event.payload.text), onClick: ctx.focusSidePanel });
      return;

    case 'conflict.opened':
      notify({
        category: 'decisions',
        title: 'Your vote is needed',
        body: clip(event.payload.options.join(' vs ')),
        onClick: ctx.focusSidePanel,
      });
      return;

    case 'conflict.closed':
      notify({ category: 'decisions', tone: 'ok', title: 'Vote closed', body: clip(event.payload.result) });
      return;

    default:
      return;
  }
}
