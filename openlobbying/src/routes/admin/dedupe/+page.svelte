<script lang="ts">
	import { enhance } from '$app/forms';
	import { resolve } from '$app/paths';
	import Properties from '$lib/components/Properties.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import type { DedupeCandidate, Entity } from '$lib/types';

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

	function getName(entity: Entity): string {
		return String(entity.properties.name?.[0] ?? entity.caption ?? entity.id);
	}

	function getDatasetTitles(entity: Entity): string[] {
		return (entity.datasets ?? []).map((dataset) => dataset.title || dataset.name);
	}

	function getDetailsHref(entity: Entity): string {
		if (['Person', 'Company', 'Organization', 'PublicBody', 'LegalEntity'].includes(entity.schema)) {
			return resolve('/profile/[id]', { id: entity.id });
		}

		return resolve('/statement/[id]', { id: entity.id });
	}

	function formatLockExpiry(expiresAt?: string): string | null {
		if (!expiresAt) {
			return null;
		}

		const parsed = new Date(expiresAt);
		if (Number.isNaN(parsed.getTime())) {
			return null;
		}

		return parsed.toLocaleString('en-GB');
	}
</script>

<svelte:head>
	<title>Dedupe Review - OpenLobbying</title>
	<meta
		name="description"
		content="Review nomenklatura deduplication candidates from the OpenLobbying admin panel."
	/>
</svelte:head>

<div class="bg-[radial-gradient(circle_at_top,_rgba(180,83,9,0.12),_transparent_42%),linear-gradient(180deg,#fffaf2_0%,#ffffff_38%,#f8fafc_100%)] px-4 py-14 sm:px-6">
	<div class="mx-auto max-w-7xl space-y-6">
		<div class="flex flex-wrap items-start justify-between gap-4">
			<div class="space-y-3">
				<p class="text-sm font-semibold uppercase tracking-[0.24em] text-amber-700">Admin / Dedupe</p>
				<h1 class="text-4xl font-semibold tracking-tight text-slate-900">Review entity matches</h1>
				<p class="max-w-3xl text-base leading-7 text-slate-600">
					This view uses nomenklatura under the hood and records the same resolver judgements as the
					terminal UI.
				</p>
			</div>

			<a
				href={resolve('/admin')}
				class="inline-flex h-10 items-center justify-center rounded-full border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition-colors hover:border-slate-300 hover:text-slate-900"
			>
				Back to admin
			</a>
		</div>

		{#if form?.error}
			<p class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
				{form.error}
			</p>
		{/if}

		{#if form?.success}
			<p class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
				{form.success}
			</p>
		{/if}

		{#if candidate}
			<div class="flex flex-wrap items-center gap-3 rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-900">
				<Badge variant="secondary">Pending pair</Badge>
				{#if candidate.score !== null && candidate.score !== undefined}
					<span>Similarity score: {candidate.score.toFixed(3)}</span>
				{/if}
				{#if lockExpiresAt}
					<span>Locked to you until {lockExpiresAt}</span>
				{/if}
			</div>

			<form method="POST" action="?/judge" use:enhance class="space-y-6">
				<input type="hidden" name="leftId" value={candidate.left.id} />
				<input type="hidden" name="rightId" value={candidate.right.id} />

				<div class="grid gap-6 lg:grid-cols-2">
					<Card class="rounded-3xl border-slate-200 bg-white/90 shadow-sm backdrop-blur">
						<CardHeader class="space-y-4">
							<div class="flex flex-wrap items-start justify-between gap-3">
								<div class="space-y-2">
									<CardTitle class="text-2xl text-slate-900">{getName(candidate.left)}</CardTitle>
									<CardDescription class="font-mono text-xs text-slate-500">
										{candidate.left.id}
									</CardDescription>
								</div>
								<Badge variant="secondary">{candidate.left.schema}</Badge>
							</div>

							<div class="flex flex-wrap gap-2">
								{#each getDatasetTitles(candidate.left) as title (title)}
									<Badge variant="secondary">{title}</Badge>
								{/each}
							</div>

							<a
								href={getDetailsHref(candidate.left)}
								class="text-sm font-medium text-amber-800 underline decoration-amber-300 underline-offset-4 transition-colors hover:text-amber-950"
							>
								Open full record
							</a>
						</CardHeader>
						<CardContent>
							<Properties properties={candidate.left.properties} type={candidate.left.schema} />
						</CardContent>
					</Card>

					<Card class="rounded-3xl border-slate-200 bg-white/90 shadow-sm backdrop-blur">
						<CardHeader class="space-y-4">
							<div class="flex flex-wrap items-start justify-between gap-3">
								<div class="space-y-2">
									<CardTitle class="text-2xl text-slate-900">{getName(candidate.right)}</CardTitle>
									<CardDescription class="font-mono text-xs text-slate-500">
										{candidate.right.id}
									</CardDescription>
								</div>
								<Badge variant="secondary">{candidate.right.schema}</Badge>
							</div>

							<div class="flex flex-wrap gap-2">
								{#each getDatasetTitles(candidate.right) as title (title)}
									<Badge variant="secondary">{title}</Badge>
								{/each}
							</div>

							<a
								href={getDetailsHref(candidate.right)}
								class="text-sm font-medium text-amber-800 underline decoration-amber-300 underline-offset-4 transition-colors hover:text-amber-950"
							>
								Open full record
							</a>
						</CardHeader>
						<CardContent>
							<Properties properties={candidate.right.properties} type={candidate.right.schema} />
						</CardContent>
					</Card>
				</div>

				<Card class="rounded-3xl border-slate-200 bg-slate-950 text-slate-50 shadow-lg">
					<CardHeader>
						<CardTitle>Record a judgement</CardTitle>
						<CardDescription class="text-slate-300">
							Choose the same outcome you would pick in the nomenklatura TUI, then the next pair
							loads immediately.
						</CardDescription>
					</CardHeader>
					<CardContent class="flex flex-wrap gap-3">
						<Button type="submit" name="judgement" value="positive" class="min-w-32 bg-emerald-600 text-white hover:bg-emerald-500">
							Match
						</Button>
						<Button type="submit" name="judgement" value="negative" variant="secondary" class="min-w-32 border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800">
							No match
						</Button>
						<Button type="submit" name="judgement" value="unsure" variant="outline" class="min-w-32 border-amber-400 bg-amber-100 text-amber-950 hover:bg-amber-200">
							Unsure
						</Button>
					</CardContent>
				</Card>
			</form>
		{:else}
			<Card class="rounded-3xl border-emerald-200 bg-emerald-50/80 shadow-sm">
				<CardHeader>
					<CardTitle class="text-2xl text-emerald-950">No pending candidates</CardTitle>
					<CardDescription class="text-emerald-900">
						Nomenklatura did not return any unresolved dedupe pairs. Run xref again if you expect
						more suggestions.
					</CardDescription>
				</CardHeader>
			</Card>
		{/if}
	</div>
</div>
