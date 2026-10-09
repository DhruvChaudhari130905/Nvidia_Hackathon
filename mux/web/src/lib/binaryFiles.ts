// Room files are strings. A binary file (an image, a font) is kept as a base64 data URL,
// `data:<mime>;base64,<bytes>`, so it travels through the files API, the event log and browser storage
// like any other file. Anything that needs the real bytes (the WebContainer, downloads, exports) decodes it.

const MIME: Record<string, string> = {
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp', avif: 'image/avif',
  svg: 'image/svg+xml', ico: 'image/x-icon', bmp: 'image/bmp', tif: 'image/tiff', tiff: 'image/tiff',
  woff: 'font/woff', woff2: 'font/woff2', ttf: 'font/ttf', otf: 'font/otf', eot: 'application/vnd.ms-fontobject',
  mp3: 'audio/mpeg', wav: 'audio/wav', ogg: 'audio/ogg', mp4: 'video/mp4', webm: 'video/webm', pdf: 'application/pdf',
};

const DATA_URL = /^data:([\w.+-]+\/[\w.+-]+);base64,([A-Za-z0-9+/]*={0,2})$/;

// Extensions a room keeps as binary (imports, uploads, files a shell command writes)
export const BINARY_ASSET = /\.(png|jpe?g|gif|webp|avif|ico|bmp|tiff?|woff2?|ttf|otf|eot|mp3|wav|ogg|mp4|webm|pdf)$/i;

// Size caps for a room file: text stays small enough to edit; images, fonts and media may be larger
export const MAX_TEXT_BYTES = 1_000_000;
export const MAX_ASSET_BYTES = 2_000_000;

export function maxBytesFor(path: string): number {
  return BINARY_ASSET.test(path) ? MAX_ASSET_BYTES : MAX_TEXT_BYTES;
}

export function mimeFor(path: string): string {
  return MIME[path.split('.').pop()!.toLowerCase()] ?? 'application/octet-stream';
}

export function isBinaryContent(content: string | undefined): boolean {
  return !!content && content.startsWith('data:') && DATA_URL.test(content);
}

export function isImagePath(path: string): boolean {
  return mimeFor(path).startsWith('image/');
}

export function bytesToDataUrl(bytes: Uint8Array, path: string): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return `data:${mimeFor(path)};base64,${btoa(binary)}`;
}

export function dataUrlToBytes(content: string): Uint8Array {
  const binary = atob(content.slice(content.indexOf(',') + 1));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

// What to write to disk or into the container for a room file
export function fileBytes(content: string): Uint8Array | string {
  return isBinaryContent(content) ? dataUrlToBytes(content) : content;
}
