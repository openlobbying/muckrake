// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
import type { Session, User } from 'better-auth';

type AuthUser = User & {
	role?: string | null;
	banned?: boolean | null;
	banReason?: string | null;
	banExpires?: Date | null;
};

declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			session: Session | null;
			user: AuthUser | null;
		}
		interface PageData {
			session: Session | null;
			user: AuthUser | null;
		}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};
