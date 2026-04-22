<script lang="ts">
	import { goto } from '$app/navigation';
	import { authClient } from '$lib/auth-client';
	import { Button } from '$lib/components/ui/button';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';

	interface AccountPageData {
		session: App.PageData['session'];
		user: App.PageData['user'];
	}

	let { data }: { data: AccountPageData } = $props();
	let isSigningOut = $state(false);

	async function signOut(): Promise<void> {
		isSigningOut = true;

		try {
			await authClient.signOut();
			await goto('/login', { invalidateAll: true });
		} finally {
			isSigningOut = false;
		}
	}
</script>

<svelte:head>
	<title>Account - OpenLobbying</title>
	<meta
		name="description"
		content="A protected page that is only available to authenticated OpenLobbying users."
	/>
	<meta name="robots" content="noindex,nofollow" />
</svelte:head>

<div class="bg-gradient-to-b from-white via-slate-50 to-amber-50 px-4 py-14 sm:px-6">
	<div class="mx-auto max-w-4xl space-y-6">
		<div class="space-y-3">
			<p class="text-sm font-semibold uppercase tracking-[0.24em] text-amber-700">Account</p>
			<h1 class="text-4xl font-semibold tracking-tight text-slate-900">
				User account
			</h1>
		</div>

		<div class="grid gap-6 md:grid-cols-2">
			<Card class="rounded-3xl">
				<CardHeader>
					<CardTitle>User</CardTitle>
					<CardDescription>User account information.</CardDescription>
				</CardHeader>
				<CardContent class="space-y-3 text-sm text-slate-600">
					<p><span class="font-medium text-slate-900">Name:</span> {data.user?.name}</p>
					<p><span class="font-medium text-slate-900">Email:</span> {data.user?.email}</p>
					<p><span class="font-medium text-slate-900">Role:</span> {data.user?.role ?? 'user'}</p>
					<p><span class="font-medium text-slate-900">User ID:</span> {data.user?.id}</p>
				</CardContent>
			</Card>

			<Card class="rounded-3xl">
				<CardHeader>
					<CardTitle>Session</CardTitle>
					<CardDescription>Server-rendered session details for the current request.</CardDescription>
				</CardHeader>
				<CardContent class="space-y-3 text-sm text-slate-600">
					<p><span class="font-medium text-slate-900">Session ID:</span> {data.session?.id}</p>
					<p>
						<span class="font-medium text-slate-900">Expires:</span>
						{data.session?.expiresAt ? new Date(data.session.expiresAt).toLocaleString('en-GB') : 'Unknown'}
					</p>
					<Button type="button" class="mt-3" onclick={signOut} disabled={isSigningOut}>
						{isSigningOut ? 'Signing out...' : 'Sign out'}
					</Button>
				</CardContent>
			</Card>
		</div>
	</div>
</div>
