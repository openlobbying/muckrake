<script lang="ts">
	import { goto } from '$app/navigation';
	import { authClient } from '$lib/auth-client';
	import { Button } from '$lib/components/ui/button';
	import {
		Card,
		CardContent,
		CardDescription,
		CardFooter,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';

	type Mode = 'login' | 'signup';

	interface LoginPageData {
		redirectTo: string;
	}

	let { data }: { data: LoginPageData } = $props();

	let mode = $state<Mode>('login');
	let name = $state('');
	let email = $state('');
	let password = $state('');
	let confirmPassword = $state('');
	let errorMessage = $state<string | null>(null);
	let successMessage = $state<string | null>(null);
	let isSubmitting = $state(false);

	const cardTitle = $derived(mode === 'login' ? 'Log in' : 'Create an account');
	const cardDescription = $derived(
		mode === 'login'
			? 'Use your email address and password to access protected pages.'
			: 'Create a password-based account stored in the OpenLobbying database.'
	);
	const submitLabel = $derived(mode === 'login' ? 'Log in' : 'Create account');
	const alternateLabel = $derived(mode === 'login' ? 'Need an account?' : 'Already registered?');
	const alternateActionLabel = $derived(mode === 'login' ? 'Sign up' : 'Log in');

	function resetMessages(): void {
		errorMessage = null;
		successMessage = null;
	}

	function switchMode(nextMode: Mode): void {
		mode = nextMode;
		resetMessages();
	}

	async function handleSubmit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		resetMessages();

		if (!email || !password) {
			errorMessage = 'Email and password are required.';
			return;
		}

		if (mode === 'signup') {
			if (!name.trim()) {
				errorMessage = 'Name is required to create an account.';
				return;
			}

			if (password !== confirmPassword) {
				errorMessage = 'Passwords do not match.';
				return;
			}
		}

		isSubmitting = true;

		try {
			if (mode === 'login') {
				const result = await authClient.signIn.email({
					email,
					password,
					rememberMe: true
				});

				if (result.error) {
					errorMessage = result.error.message ?? 'Unable to log in.';
					return;
				}

				await goto(data.redirectTo, { invalidateAll: true });
				return;
			}

			const result = await authClient.signUp.email({
				name: name.trim(),
				email,
				password
			});

			if (result.error) {
				errorMessage = result.error.message ?? 'Unable to create account.';
				return;
			}

			successMessage = 'Account created. Redirecting...';
			await goto(data.redirectTo, { invalidateAll: true });
		} finally {
			isSubmitting = false;
		}
	}
</script>

<svelte:head>
	<title>Login - OpenLobbying</title>
	<meta
		name="description"
		content="Log in to access protected OpenLobbying pages backed by Better Auth."
	/>
</svelte:head>

<div class="bg-gradient-to-b from-slate-50 via-white to-amber-50 px-4 py-14 sm:px-6">
	<div class="mx-auto grid max-w-5xl gap-8 lg:grid-cols-[1.15fr_0.85fr]">
		<section class="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
			<p class="text-sm font-semibold uppercase tracking-[0.24em] text-amber-700">Protected access</p>
			<h1 class="mt-4 max-w-xl text-4xl font-semibold tracking-tight text-slate-900">
				Sign in to reach internal pages
			</h1>
			<p class="mt-4 max-w-2xl text-base leading-7 text-slate-600">
				This is a minimal Better Auth setup using email and password credentials. Accounts and
				sessions are stored in the Postgres database configured through
				<code>MUCKRAKE_DATABASE_URL</code>.
			</p>

			<div class="mt-8 grid gap-4 sm:grid-cols-2">
				<div class="rounded-2xl border border-slate-200 bg-slate-50 p-5">
					<p class="text-sm font-semibold text-slate-900">Route protection</p>
					<p class="mt-2 text-sm leading-6 text-slate-600">
						The <code>/account</code> page redirects anonymous visitors back here.
					</p>
				</div>
				<div class="rounded-2xl border border-slate-200 bg-slate-50 p-5">
					<p class="text-sm font-semibold text-slate-900">Cookie sessions</p>
					<p class="mt-2 text-sm leading-6 text-slate-600">
						Better Auth manages the session cookie and the SvelteKit hook loads the current user
						into <code>event.locals</code>.
					</p>
				</div>
			</div>
		</section>

		<Card class="rounded-3xl border-slate-200 shadow-sm">
			<CardHeader class="space-y-2">
				<CardTitle class="text-2xl">{cardTitle}</CardTitle>
				<CardDescription>{cardDescription}</CardDescription>
			</CardHeader>
			<CardContent>
				<form class="space-y-4" onsubmit={handleSubmit}>
					{#if mode === 'signup'}
						<label class="block space-y-2">
							<span class="text-sm font-medium text-slate-700">Name</span>
							<Input bind:value={name} autocomplete="name" placeholder="OpenLobbying user" />
						</label>
					{/if}

					<label class="block space-y-2">
						<span class="text-sm font-medium text-slate-700">Email</span>
						<Input
							bind:value={email}
							type="email"
							autocomplete="email"
							placeholder="name@example.org"
						/>
					</label>

					<label class="block space-y-2">
						<span class="text-sm font-medium text-slate-700">Password</span>
						<Input
							bind:value={password}
							type="password"
							autocomplete={mode === 'login' ? 'current-password' : 'new-password'}
							placeholder="At least 8 characters"
						/>
					</label>

					{#if mode === 'signup'}
						<label class="block space-y-2">
							<span class="text-sm font-medium text-slate-700">Confirm password</span>
							<Input
								bind:value={confirmPassword}
								type="password"
								autocomplete="new-password"
								placeholder="Repeat the password"
							/>
						</label>
					{/if}

					{#if errorMessage}
						<p class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
							{errorMessage}
						</p>
					{/if}

					{#if successMessage}
						<p class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
							{successMessage}
						</p>
					{/if}

					<Button type="submit" class="w-full" disabled={isSubmitting}>
						{isSubmitting ? 'Submitting...' : submitLabel}
					</Button>
				</form>
			</CardContent>
			<CardFooter class="flex items-center justify-between gap-3 border-t border-slate-200 pt-6">
				<p class="text-sm text-slate-500">{alternateLabel}</p>
				<Button
					type="button"
					variant="ghost"
					onclick={() => {
						switchMode(mode === 'login' ? 'signup' : 'login');
					}}
				>
					{alternateActionLabel}
				</Button>
			</CardFooter>
		</Card>
	</div>
</div>
