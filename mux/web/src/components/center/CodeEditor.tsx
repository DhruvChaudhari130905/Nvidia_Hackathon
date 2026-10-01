'use client';

import React, { useEffect, useRef } from 'react';
import Editor, { type BeforeMount, type OnMount } from '@monaco-editor/react';

// Monaco editor for one open file. The parent owns unsaved drafts (so switching tabs keeps them);
// this component just renders the draft or the saved content and reports edits, saves and cursor moves.

export function languageFor(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'ts':
    case 'tsx':
      return 'typescript';
    case 'js':
    case 'jsx':
    case 'mjs':
    case 'cjs':
      return 'javascript';
    case 'css':
      return 'css';
    case 'scss':
      return 'scss';
    case 'json':
      return 'json';
    case 'html':
      return 'html';
    case 'md':
      return 'markdown';
    case 'py':
      return 'python';
    case 'yml':
    case 'yaml':
      return 'yaml';
    case 'sql':
      return 'sql';
    default:
      return 'plaintext';
  }
}

// Theme matching the room's GitHub-dark tokens, plus TypeScript settings for a sandbox without node_modules
const defineTheme: BeforeMount = monaco => {
  for (const defaults of [monaco.languages.typescript.typescriptDefaults, monaco.languages.typescript.javascriptDefaults]) {
    defaults.setCompilerOptions({
      target: monaco.languages.typescript.ScriptTarget.ES2020,
      jsx: monaco.languages.typescript.JsxEmit.ReactJSX,
      allowJs: true,
      allowNonTsExtensions: true,
      moduleResolution: monaco.languages.typescript.ModuleResolutionKind.NodeJs,
      esModuleInterop: true,
    });
    // Packages aren't installed in the browser, so only syntax errors are meaningful here
    defaults.setDiagnosticsOptions({ noSemanticValidation: true, noSyntaxValidation: false });
  }
  monaco.editor.defineTheme('mux-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '8b949e', fontStyle: 'italic' },
      { token: 'keyword', foreground: 'ff7b72' },
      { token: 'string', foreground: 'a5d6ff' },
      { token: 'number', foreground: '79c0ff' },
      { token: 'type', foreground: 'ffa657' },
      { token: 'tag', foreground: '7ee787' },
      { token: 'attribute.name', foreground: '79c0ff' },
      { token: 'delimiter', foreground: 'c9d1d9' },
    ],
    colors: {
      'editor.background': '#010409',
      'editor.foreground': '#e6edf3',
      'editorLineNumber.foreground': '#484f58',
      'editorLineNumber.activeForeground': '#e6edf3',
      'editor.lineHighlightBackground': '#161b2280',
      'editor.selectionBackground': '#3b82f640',
      'editor.inactiveSelectionBackground': '#3b82f620',
      'editorCursor.foreground': '#06b6d4',
      'editorIndentGuide.background1': '#21262d',
      'editorIndentGuide.activeBackground1': '#30363d',
      'editorWidget.background': '#0d1117',
      'editorWidget.border': '#30363d',
      'scrollbarSlider.background': '#30363d80',
      'scrollbarSlider.hoverBackground': '#484f58',
    },
  });
};

export type EditorShortcut = 'save' | 'format' | 'quickOpen' | 'palette' | 'toggleTerminal' | 'run';

export interface EditorSettings {
  wordWrap: boolean;
  minimap: boolean;
  fontSize: number;
}

interface CodeEditorProps {
  path: string;
  value: string;
  isLocked: boolean;
  settings: EditorSettings;
  onChange: (value: string) => void;
  onShortcut: (action: EditorShortcut) => void;
  onCursor: (line: number, column: number) => void;
  onReady: (editor: Parameters<OnMount>[0], monaco: Parameters<OnMount>[1]) => void;
}

export function CodeEditor({ path, value, isLocked, settings, onChange, onShortcut, onCursor, onReady }: CodeEditorProps) {
  // Monaco commands are registered once; refs keep them pointing at the latest callbacks
  const shortcutRef = useRef(onShortcut);
  const cursorRef = useRef(onCursor);
  useEffect(() => {
    shortcutRef.current = onShortcut;
    cursorRef.current = onCursor;
  });

  const handleMount: OnMount = (editor, monaco) => {
    const { KeyMod, KeyCode } = monaco;
    editor.addCommand(KeyMod.CtrlCmd | KeyCode.KeyS, () => shortcutRef.current('save'));
    editor.addCommand(KeyMod.Shift | KeyMod.Alt | KeyCode.KeyF, () => shortcutRef.current('format'));
    editor.addCommand(KeyMod.CtrlCmd | KeyCode.KeyP, () => shortcutRef.current('quickOpen'));
    editor.addCommand(KeyMod.CtrlCmd | KeyMod.Shift | KeyCode.KeyP, () => shortcutRef.current('palette'));
    editor.addCommand(KeyMod.WinCtrl | KeyCode.Backquote, () => shortcutRef.current('toggleTerminal'));
    editor.addCommand(KeyCode.F5, () => shortcutRef.current('run'));
    editor.onDidChangeCursorPosition(e => cursorRef.current(e.position.lineNumber, e.position.column));
    onReady(editor, monaco);
    editor.focus();
  };

  return (
    <div className="min-h-0 flex-1">
      <Editor
        height="100%"
        path={path}
        // One model per file, kept when switching tabs: undo history survives and Problems covers every opened file
        keepCurrentModel
        language={languageFor(path)}
        value={value}
        onChange={v => onChange(v ?? '')}
        theme="mux-dark"
        beforeMount={defineTheme}
        onMount={handleMount}
        loading={
          <div className="flex h-full items-center justify-center gap-2 font-mono text-xs text-[var(--muted)]">
            <span className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-[var(--coder)] border-t-transparent" />
            Loading editor…
          </div>
        }
        options={{
          minimap: { enabled: settings.minimap, scale: 1, renderCharacters: false },
          fontSize: settings.fontSize,
          wordWrap: settings.wordWrap ? 'on' : 'off',
          fontFamily: '"IBM Plex Mono", ui-monospace, Menlo, monospace',
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
          readOnly: isLocked,
          smoothScrolling: true,
          cursorBlinking: 'smooth',
          cursorSmoothCaretAnimation: 'on',
          renderLineHighlight: 'all',
          bracketPairColorization: { enabled: true },
          guides: { bracketPairs: true, indentation: true },
          padding: { top: 12, bottom: 12 },
          stickyScroll: { enabled: true },
        }}
      />
    </div>
  );
}
