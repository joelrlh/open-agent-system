import corpusDocument from "../../../mcp/research_fixture/content/corpus.json";
import { z } from "zod";

export const CANONICAL_HOST = "research.fixture.test";
export const MAX_QUERY_CHARS = 200;
export const MAX_RESULTS = 5;
export const MAX_CONTENT_BYTES = 4 * 1024;

const SOURCE_ID_PATTERN = /^[a-z][a-z0-9-]{0,62}$/;
const encoder = new TextEncoder();

const SourceSchema = z.strictObject({
  source_id: z.string().min(1).max(63).regex(SOURCE_ID_PATTERN),
  title: z.string().min(1).max(160),
  summary: z.string().min(1).max(1024),
  content: z.string().min(1),
  injection_detected: z.boolean().default(false),
});

const CorpusDocumentSchema = z.strictObject({
  schema_version: z.literal(1),
  sources: z.array(SourceSchema).min(1).max(50),
});

const SearchRequestSchema = z.strictObject({
  query: z.string().min(1).max(MAX_QUERY_CHARS),
  limit: z.number().int().min(1).max(MAX_RESULTS).default(3),
});

const FetchRequestSchema = z.strictObject({
  uri: z.string().min(1).max(256),
});

export const SearchInputSchema = SearchRequestSchema;
export const FetchInputSchema = FetchRequestSchema;

export class FixtureError extends Error {}

export function validateCorpus(input: unknown) {
  const result = CorpusDocumentSchema.safeParse(input);
  if (!result.success) {
    throw new FixtureError("invalid corpus");
  }
  const identifiers = new Set(result.data.sources.map((source) => source.source_id));
  if (identifiers.size !== result.data.sources.length) {
    throw new FixtureError("duplicate source_id in corpus");
  }
  for (const source of result.data.sources) {
    if (encoder.encode(source.content).byteLength > MAX_CONTENT_BYTES) {
      throw new FixtureError(`source content exceeds byte cap: ${source.source_id}`);
    }
  }
  return result.data;
}

const parsedCorpus = validateCorpus(corpusDocument);
const sources = new Map(parsedCorpus.sources.map((source) => [source.source_id, source]));

export function sourceIdFromUri(uri: string): string {
  const request = FetchRequestSchema.safeParse({ uri });
  if (!request.success) {
    throw new FixtureError("invalid fetch request");
  }

  const authority = /^https:\/\/([^/?#]+)/.exec(request.data.uri);
  let parsed: URL;
  try {
    parsed = new URL(request.data.uri);
  } catch {
    throw new FixtureError("fetch URI contains an invalid authority");
  }

  if (
    authority?.[1] !== CANONICAL_HOST ||
    parsed.protocol !== "https:" ||
    parsed.hostname !== CANONICAL_HOST
  ) {
    throw new FixtureError("fetch URI is outside the deterministic fixture origin");
  }
  if (parsed.username || parsed.password || parsed.port || parsed.search || parsed.hash) {
    throw new FixtureError("fetch URI contains a forbidden authority or suffix");
  }

  const pathMatch = /^\/sources\/([^/]+)$/.exec(parsed.pathname);
  if (!pathMatch) {
    throw new FixtureError("fetch URI does not identify one fixture source");
  }
  const sourceId = pathMatch[1];
  if (!SOURCE_ID_PATTERN.test(sourceId)) {
    throw new FixtureError("invalid source identifier");
  }
  return sourceId;
}

export function searchCorpus(input: unknown) {
  const request = SearchRequestSchema.safeParse(input);
  if (!request.success) {
    throw new FixtureError("invalid search request");
  }

  const terms = new Set(request.data.query.toLowerCase().match(/[a-z0-9]+/g) ?? []);
  const ranked = parsedCorpus.sources
    .map((source) => {
      const haystack = `${source.title} ${source.summary} ${source.content}`.toLowerCase();
      const score = [...terms].filter((term) => haystack.includes(term)).length;
      return { score, source };
    })
    .filter(({ score }) => score > 0)
    .sort(
      (left, right) =>
        right.score - left.score || left.source.source_id.localeCompare(right.source.source_id),
    );

  const results = ranked.slice(0, request.data.limit).map(({ source }) => ({
    excerpt: source.summary,
    injection_detected: source.injection_detected,
    source_id: source.source_id,
    title: source.title,
    uri: `https://${CANONICAL_HOST}/sources/${source.source_id}`,
  }));

  return {
    count: results.length,
    query: request.data.query,
    results,
    status: "ok" as const,
    truncated: ranked.length > request.data.limit,
  };
}

export function fetchCorpus(input: unknown) {
  const request = FetchRequestSchema.safeParse(input);
  if (!request.success) {
    throw new FixtureError("invalid fetch request");
  }
  const sourceId = sourceIdFromUri(request.data.uri);
  const source = sources.get(sourceId);
  if (!source) {
    throw new FixtureError("unknown source identifier");
  }

  return {
    content: source.content,
    injection_detected: source.injection_detected,
    source_id: source.source_id,
    status: "ok" as const,
    title: source.title,
    truncated: false,
    uri: `https://${CANONICAL_HOST}/sources/${source.source_id}`,
  };
}

async function sha256(value: string): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(value)));
}

export async function hasValidBearerToken(
  authorization: string | null,
  token: string | undefined,
): Promise<boolean> {
  if (!authorization || !token || encoder.encode(token).byteLength < 24) {
    return false;
  }
  const [actual, expected] = await Promise.all([sha256(authorization), sha256(`Bearer ${token}`)]);
  let difference = 0;
  for (let index = 0; index < expected.length; index += 1) {
    difference |= actual[index] ^ expected[index];
  }
  return difference === 0;
}
