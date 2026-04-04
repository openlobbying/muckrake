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
	import type { DedupeClusterCandidate, Entity } from '$lib/types';
	import { getEntityRoute } from '$lib/util/routes';

	interface DedupeClustersPageData {
		candidate: DedupeClusterCandidate | null;
	}

	interface DedupeClustersActionData {
		error?: string;
		success?: string;
	}

	let { data, form }: { data: DedupeClustersPageData; form: DedupeClustersActionData | null } =
		$props();
	let candidate = $derived(data.candidate);
	let lockExpiresAt = $derived(formatLockExpiry(candidate?.lock_expires_at));

	function getName(entity: Entity): string {
		return String(entity.properties.name?.[0] ?? entity.caption ?? entity.id);
	}

	function getDatasetTitles(entity: Entity): string[] {
		return (entity.datasets ?? []).map((dataset) => dataset.title || dataset.name);
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
	<title>Dedupe Clusters - OpenLobbying</title>
	<meta
		name="description"
		content="Review clustered nomenklatura deduplication candidates from the OpenLobbying admin panel."
	/>
</svelte:head>

<div class="bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.14),_transparent_40%),linear-gradient(180deg,#f8fbff_0%,#ffffff_42%,#f8fafc_100%)] px-4 py-14 sm:px-6">
	<div class="mx-auto max-w-7xl space-y-6">
		<div class="flex flex-wrap items-start justify-between gap-4">
			<div class="space-y-3">
				<p class="text-sm font-semibold uppercase tracking-[0.24em] text-sky-700">
					Admin / Dedupe Clusters
				</p>
				<h1 class="text-4xl font-semibold tracking-tight text-slate-900">Review grouped entity matches</h1>
				<p class="max-w-3xl text-base leading-7 text-slate-600">
					This MVP groups a small set of connected resolver suggestions, then lets you tick only the
					records that should merge.
				</p>
			</div>

			<div class="flex flex-wrap gap-3">
				<a
					href={resolve('/admin/dedupe')}
					class="inline-flex h-10 items-center justify-center rounded-full border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition-colors hover:border-slate-300 hover:text-slate-900"
				>
					Open pair queue
				</a>
				<a
					href={resolve('/admin')}
					class="inline-flex h-10 items-center justify-center rounded-full border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition-colors hover:border-slate-300 hover:text-slate-900"
				>
					Back to admin
				</a>
			</div>
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
			<div class="flex flex-wrap items-center gap-3 rounded-2xl border border-sky-200 bg-sky-50/80 px-4 py-3 text-sm text-sky-950">
				<Badge variant="secondary">Cluster MVP</Badge>
				<span>{candidate.members.length} records in this batch</span>
				<span>{candidate.locked_pairs.length} unresolved edges locked</span>
				{#if lockExpiresAt}
					<span>Locked to you until {lockExpiresAt}</span>
				{/if}
			</div>

			<form method="POST" action="?/merge" use:enhance class="space-y-6">
				{#each candidate.members as member (member.entity.id)}
					<input type="hidden" name="entityId" value={member.entity.id} />
				{/each}
				{#each candidate.locked_pairs as pair (`${pair.left_id}::${pair.right_id}`)}
					<input type="hidden" name="lockedPair" value={`${pair.left_id}::${pair.right_id}`} />
				{/each}

				<div class="grid gap-6 xl:grid-cols-2">
					{#each candidate.members as member (member.entity.id)}
						<Card class="rounded-3xl border-slate-200 bg-white/95 shadow-sm backdrop-blur">
							<CardHeader class="space-y-4">
								<div class="flex items-start justify-between gap-3">
									<label class="flex items-start gap-3 text-sm text-slate-700">
										<input
											type="checkbox"
											name="selectedId"
											value={member.entity.id}
											checked
											class="mt-1 h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
										/>
										<span>
											<span class="block text-xs font-semibold uppercase tracking-[0.22em] text-sky-700">
												Merge this record
											</span>
											<span class="mt-1 block font-mono text-xs text-slate-500">
												{member.entity.id}
											</span>
										</span>
									</label>
									<Badge variant="secondary">{member.entity.schema}</Badge>
								</div>

								<div class="space-y-2">
									<CardTitle class="text-2xl text-slate-900">{getName(member.entity)}</CardTitle>
									{#if member.score !== null && member.score !== undefined}
										<CardDescription class="text-sky-800">
											Best linked score: {member.score.toFixed(3)}
										</CardDescription>
									{/if}
								</div>

								<div class="flex flex-wrap gap-2">
									{#each getDatasetTitles(member.entity) as title (title)}
										<Badge variant="secondary">{title}</Badge>
									{/each}
								</div>

								<a
									href={getEntityRoute(member.entity.id, member.entity.schema)}
									class="text-sm font-medium text-sky-800 underline decoration-sky-300 underline-offset-4 transition-colors hover:text-sky-950"
								>
									Open full record
								</a>
							</CardHeader>
							<CardContent>
								<Properties properties={member.entity.properties} type={member.entity.schema} />
							</CardContent>
						</Card>
					{/each}
				</div>

				<Card class="rounded-3xl border-slate-200 bg-slate-950 text-slate-50 shadow-lg">
					<CardHeader>
						<CardTitle>Merge selected records</CardTitle>
						<CardDescription class="text-slate-300">
							Leave obvious outliers unchecked. When you merge a subset, unchecked records are stored
							as no-match decisions against the merged group. Submitting with fewer than two selected
							records just releases this cluster back to the queue.
						</CardDescription>
					</CardHeader>
					<CardContent class="flex flex-wrap gap-3">
						<Button
							type="submit"
							name="intent"
							value="merge"
							class="min-w-40 bg-sky-600 text-white hover:bg-sky-500"
						>
							Merge selected
						</Button>
						<Button
							type="submit"
							name="intent"
							value="skip"
							variant="secondary"
							class="min-w-32 border border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"
						>
							Skip cluster
						</Button>
					</CardContent>
				</Card>
			</form>
		{:else}
			<Card class="rounded-3xl border-emerald-200 bg-emerald-50/80 shadow-sm">
				<CardHeader>
					<CardTitle class="text-2xl text-emerald-950">No pending clusters</CardTitle>
					<CardDescription class="text-emerald-900">
						The clustered MVP did not find any unresolved local groups in the current suggestion window.
					</CardDescription>
				</CardHeader>
			</Card>
		{/if}
	</div>
</div>
