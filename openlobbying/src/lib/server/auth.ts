import { dev } from '$app/environment';
import { getRequestEvent } from '$app/server';
import { env } from '$env/dynamic/private';
import { betterAuth } from 'better-auth';
import { getMigrations } from 'better-auth/db/migration';
import { admin } from 'better-auth/plugins';
import { sveltekitCookies } from 'better-auth/svelte-kit';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Pool } from 'pg';

export const ADMIN_USER_ID = 'o2uOrNOs9d8OLvpxWWOIynfNpYRiChoc';

function readEnvFile(fileUrl: URL): Record<string, string> {
	try {
		const file = readFileSync(fileURLToPath(fileUrl), 'utf8');
		const values: Record<string, string> = {};

		for (const line of file.split('\n')) {
			const trimmed = line.trim();

			if (!trimmed || trimmed.startsWith('#')) {
				continue;
			}

			const separatorIndex = trimmed.indexOf('=');
			if (separatorIndex === -1) {
				continue;
			}

			const key = trimmed.slice(0, separatorIndex).trim();
			const rawValue = trimmed.slice(separatorIndex + 1).trim();
			values[key] = rawValue.replace(/^['"]|['"]$/g, '');
		}

		return values;
	} catch {
		return {};
	}
}

const frontendEnv = readEnvFile(new URL('../../../../.env', import.meta.url));
const repoEnv = readEnvFile(new URL('../../../../../.env', import.meta.url));

export function resolveEnvValue(...keys: string[]): string | undefined {
	for (const key of keys) {
		const value =
			env[key] ??
			process.env[key] ??
			frontendEnv[key] ??
			repoEnv[key];

		if (value) {
			return value;
		}
	}

	return undefined;
}

const authSecret = resolveEnvValue('AUTH_SECRET', 'BETTER_AUTH_SECRET');
const databaseUrl = resolveEnvValue('MUCKRAKE_DATABASE_URL');

export function getAuthSecret(): string {
	if (authSecret) {
		return authSecret;
	}

	if (dev) {
		return 'openlobbying-dev-auth-secret-change-me';
	}

	throw new Error('AUTH_SECRET must be set when running OpenLobbying auth outside development.');
}

if (!databaseUrl) {
	throw new Error('MUCKRAKE_DATABASE_URL must be set to configure Better Auth.');
}

const pool = new Pool({
	connectionString: databaseUrl
});

export const auth = betterAuth({
	basePath: '/auth',
	secret: getAuthSecret(),
	database: pool,
	emailAndPassword: {
		enabled: true
	},
	plugins: [
		admin({
			adminUserIds: [ADMIN_USER_ID]
		}),
		sveltekitCookies(getRequestEvent)
	]
});

let authSchemaReady: Promise<void> | null = null;

export function ensureAuthSchema(): Promise<void> {
	if (!authSchemaReady) {
		authSchemaReady = (async () => {
			const { runMigrations } = await getMigrations(auth.options);
			await runMigrations();
		})();
	}

	return authSchemaReady;
}
