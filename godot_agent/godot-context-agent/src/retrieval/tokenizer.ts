/**
 * Rough token estimator. We are not trying to match any specific BPE; we just
 * need a stable budget signal. Empirically, code averages ~3.6 chars/token on
 * Claude and GPT-class tokenizers — we round to 4 with a tiny per-line bias.
 *
 * Accurate enough for staying under a 2k budget; ~10% slack is acceptable
 * because the consuming model's context window has its own buffer.
 */
export function estimateTokens(text: string): number {
  if (!text) return 0;
  const chars = text.length;
  const lines = text.split("\n").length;
  // chars/4 + 1 per newline as cheap "structural" overhead
  return Math.ceil(chars / 4) + lines;
}

/** Hard-trim text to a token budget, preserving line boundaries when possible. */
export function trimToTokens(text: string, maxTokens: number): string {
  if (estimateTokens(text) <= maxTokens) return text;
  // chars/4 ≈ tokens, so target chars ≈ maxTokens * 4
  const targetChars = Math.max(0, maxTokens * 4 - 32);
  const sliced = text.slice(0, targetChars);
  const lastNl = sliced.lastIndexOf("\n");
  return (lastNl > targetChars * 0.7 ? sliced.slice(0, lastNl) : sliced) + "\n# … (truncated)";
}
