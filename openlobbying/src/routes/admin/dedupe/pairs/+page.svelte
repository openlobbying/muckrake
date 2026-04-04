<script lang="ts">
	import { enhance } from '$app/forms';
	import AdminFlash from '$lib/components/admin/AdminFlash.svelte';
	import DedupeEntityCard from '$lib/components/admin/dedupe/DedupeEntityCard.svelte';
	import { formatLockExpiry } from '$lib/components/admin/dedupe/utils';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import type { DedupeCandidate } from '$lib/types';

	interface DedupePageData {
		candidate: DedupeCandidate | null;
	}

	interface DedupeActionData {
		error?: string;
		success?: string;
	}

	let { data, form }: { data: DedupePageData; form: DedupeActionData | null } = $props();
	let candidate = $derived(data.candidate);
	let lockExpiresAt = $derived(formatLockExpiry(candidate?.lock_expires_at));
</script>

<svelte:head>
	<title>Dedupe Pairs - OpenLobbying</title>
	<meta name="description" content="Review pair dedupe candidates from the OpenLobbying admin panel." />
</svelte:head>

<div class="space-y-6">
	<div class="space-y-2">
		<h2 class="text-2xl font-semibold tracking-tight text-slate-950">Dedupe pairs</h2>
		<p class="text-sm leading-6 text-slate-600">
			Review one suggested match at a time and store the same judgement as the nomenklatura terminal flow.
		</p>
	</div>

	<AdminFlash error={form?.error} success={form?.success} />

	{#if candidate}
		<div class="flex flex-wrap items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
			<Badge variant="secondary">Pending pair</Badge>
			{#if candidate.score !== null && candidate.score !== undefined}
				<span>Similarity score: {candidate.score.toFixed(3)}</span>
			{/if}
			{#if lockExpiresAt}
				<span>Locked until {lockExpiresAt}</span>
			{/if}
		</div>

		<form method="POST" action="?/judge" use:enhance class="space-y-6">
			<input type="hidden" name="leftId" value={candidate.left.id} />
			<input type="hidden" name="rightId" value={candidate.right.id} />

			<div class="grid gap-6 xl:grid-cols-2">
				<DedupeEntityCard entity={candidate.left} />
				<DedupeEntityCard entity={candidate.right} />
			</div>

			<Card class="border-slate-200">
				<CardHeader>
					<CardTitle>Record judgement</CardTitle>
					<CardDescription>Choose the outcome that best matches the evidence above.</CardDescription>
				</CardHeader>
				<CardContent class="flex flex-wrap gap-3">
					<Button type="submit" name="judgement" value="positive">Match</Button>
					<Button type="submit" name="judgement" value="negative" variant="secondary">No match</Button>
					<Button type="submit" name="judgement" value="unsure" variant="outline">Unsure</Button>
				</CardContent>
			</Card>
		</form>
	{:else}
		<Card class="border-emerald-200 bg-emerald-50">
			<CardHeader>
				<CardTitle class="text-emerald-950">No pending candidates</CardTitle>
				<CardDescription class="text-emerald-900">
					Nomenklatura did not return any unresolved dedupe pairs.
				</CardDescription>
			</CardHeader>
		</Card>
	{/if}
</div>
