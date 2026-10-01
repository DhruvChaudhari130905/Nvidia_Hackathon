// WebContainer integration for live preview
// Uses @webcontainer/api to run the full-stack app in the browser

import type { WebContainer as WebContainerInstance } from '@webcontainer/api';
import { starterProjectFiles } from './starterProject';

// Only one WebContainer can be booted per page, so every caller shares the same boot
let bootPromise: Promise<WebContainerInstance> | null = null;

export async function initWebContainer(): Promise<any> {
  if (typeof window === 'undefined') return null;
  if (!bootPromise) {
    // Dynamic import to avoid SSR issues
    bootPromise = import('@webcontainer/api')
      .then(({ WebContainer }) => WebContainer.boot({ workdirName: 'project' }))
      .catch(err => {
        bootPromise = null; // allow a retry
        throw err;
      });
  }
  return bootPromise;
}

export async function mountFiles(files: Map<string, { content: string }>): Promise<void> {
  const instance = await initWebContainer();
  if (!instance) throw new Error('WebContainer not initialized');

  // Write all files to the container
  for (const [path, file] of files) {
    await instance.fs.writeFile(path, file.content);
  }
}

export async function writeFile(path: string, content: string): Promise<void> {
  const instance = await initWebContainer();
  if (!instance) throw new Error('WebContainer not initialized');
  await instance.fs.writeFile(path, content);
}

export async function readFile(path: string): Promise<string> {
  const instance = await initWebContainer();
  if (!instance) throw new Error('WebContainer not initialized');
  return instance.fs.readFile(path, 'utf-8');
}

export async function deleteFile(path: string): Promise<void> {
  const instance = await initWebContainer();
  if (!instance) throw new Error('WebContainer not initialized');
  await instance.fs.rm(path, { recursive: true, force: true });
}

export async function runCommand(command: string, args: string[] = []): Promise<{ exitCode: number; output: string }> {
  const instance = await initWebContainer();
  if (!instance) throw new Error('WebContainer not initialized');

  const process = await instance.spawn(command, args, {
    cwd: '/',
  });

  return new Promise((resolve) => {
    let output = '';
    process.output.pipeTo(
      new WritableStream({
        write(chunk) {
          output += new TextDecoder().decode(chunk);
        },
      })
    );

    process.exit.then((exitCode: number) => {
      resolve({ exitCode, output });
    });
  });
}

export async function installDependencies(): Promise<void> {
  await runCommand('npm', ['install']);
}

export async function runDev(): Promise<void> {
  const instance = await initWebContainer();
  if (!instance) throw new Error('WebContainer not initialized');

  // Start the dev server
  const process = await instance.spawn('npm', ['run', 'dev'], {
    cwd: '/',
  });

  // Wait for the server to be ready
  await instance.waitForService('http://localhost:5173');
}

export async function getPreviewUrl(): Promise<string> {
  const instance = await initWebContainer();
  if (!instance) throw new Error('WebContainer not initialized');
  const port = await instance.waitForService('http://localhost:5173');
  return `https://${port}--${instance.id}.webcontainer.io`;
}

// For production build preview
export async function runBuild(): Promise<{ success: boolean; output: string }> {
  const result = await runCommand('npm', ['run', 'build']);
  return { success: result.exitCode === 0, output: result.output };
}

export async function runTypeCheck(): Promise<{ success: boolean; output: string }> {
  const result = await runCommand('npx', ['tsc', '--noEmit']);
  return { success: result.exitCode === 0, output: result.output };
}

// Starter template files (one definition, shared with the room page)
export function getStarterTemplate(): Map<string, { content: string }> {
  return starterProjectFiles();
}
