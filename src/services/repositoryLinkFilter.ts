const REPOSITORY_HOSTS = [
  'github.com',
  'githubusercontent.com',
  'github.io',
  'gitlab.com',
  'gitlab.io',
  'bitbucket.org',
  'sourceforge.net',
  'codeberg.org',
  'git.sr.ht',
  'huggingface.co',
];

export function isRepositoryUrl(rawUrl: string): boolean {
  const cleaned = rawUrl.trim().replace(/[),.;!?]+$/, '');
  const candidate = /^https?:\/\//i.test(cleaned) ? cleaned : `https://${cleaned}`;
  try {
    const host = new URL(candidate).hostname.toLowerCase().replace(/^www\./, '');
    return REPOSITORY_HOSTS.some(domain => host === domain || host.endsWith(`.${domain}`));
  } catch {
    return false;
  }
}

/** Remove repository links while preserving ordinary financial-news URLs and readable labels. */
export function stripRepositoryLinks(input: string): string {
  return input
    .replace(/\[([^\]]+)\]\((?:<)?(https?:\/\/[^)\s>]+)(?:>)?\)/gi,
      (whole, label: string, url: string) => isRepositoryUrl(url) ? label : whole)
    .replace(/<(https?:\/\/[^>\s]+)>/gi, (whole, url: string) => isRepositoryUrl(url) ? '' : whole)
    .replace(/https?:\/\/[^\s<>()]+/gi, (url: string) => isRepositoryUrl(url) ? '' : url)
    .replace(/(?:www\.)?(?:github\.com|githubusercontent\.com|github\.io|gitlab\.com|gitlab\.io|bitbucket\.org|sourceforge\.net|codeberg\.org|git\.sr\.ht|huggingface\.co)\/[^\s<>()\]]+/gi, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function sanitizeRepositoryLinks(value: unknown): unknown {
  if (typeof value === 'string') return stripRepositoryLinks(value);
  if (Array.isArray(value)) return value.map(sanitizeRepositoryLinks);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .map(([key, child]) => [key, sanitizeRepositoryLinks(child)]),
    );
  }
  return value;
}
