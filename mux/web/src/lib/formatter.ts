// In-browser code formatting with Prettier. Prettier and its parsers are loaded on first use.

type Parser = 'typescript' | 'babel' | 'json' | 'css' | 'scss' | 'html' | 'markdown' | 'yaml';

export function parserFor(path: string): Parser | null {
  const ext = path.split('.').pop()?.toLowerCase();
  switch (ext) {
    case 'ts':
    case 'tsx':
    case 'mts':
    case 'cts':
      return 'typescript';
    case 'js':
    case 'jsx':
    case 'mjs':
    case 'cjs':
      return 'babel';
    case 'json':
      return 'json';
    case 'css':
      return 'css';
    case 'scss':
      return 'scss';
    case 'html':
      return 'html';
    case 'md':
      return 'markdown';
    case 'yml':
    case 'yaml':
      return 'yaml';
    default:
      return null;
  }
}

export function canFormat(path: string): boolean {
  return parserFor(path) !== null;
}

// Formats `code` for the file at `path`. Throws with Prettier's message on a syntax error.
export async function formatCode(path: string, code: string): Promise<string> {
  const parser = parserFor(path);
  if (!parser) throw new Error(`No formatter for ${path.split('/').pop()}`);

  const [prettier, babel, estree, typescript, postcss, html, markdown, yaml] = await Promise.all([
    import('prettier/standalone'),
    import('prettier/plugins/babel'),
    import('prettier/plugins/estree'),
    import('prettier/plugins/typescript'),
    import('prettier/plugins/postcss'),
    import('prettier/plugins/html'),
    import('prettier/plugins/markdown'),
    import('prettier/plugins/yaml'),
  ]);

  return prettier.format(code, {
    parser,
    plugins: [babel, estree, typescript, postcss, html, markdown, yaml],
    singleQuote: true,
    semi: true,
    printWidth: 100,
    tabWidth: 2,
    trailingComma: 'all',
  });
}
