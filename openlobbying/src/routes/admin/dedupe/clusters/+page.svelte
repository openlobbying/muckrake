<script lang="ts">
	import { enhance } from '$app/forms';
	import AdminFlash from '$lib/components/admin/AdminFlash.svelte';
	import DedupeEntityCard from '$lib/components/admin/dedupe/DedupeEntityCard.svelte';
	import { formatLockExpiry } from '$lib/components/admin/dedupe/utils';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import type { DedupeClusterCandidate } from '$lib/types';

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
</script>

<svelte:head>
	<title>Dedupe Clusters - OpenLobbying</title>
	<meta name="description" content="Review grouped dedupe candidates from the OpenLobbying admin panel." />
</svelte:head>

<div class="space-y-6">
	<div class="space-y-2">
		<h2 class="text-2xl font-semibold tracking-tight text-slate-950">Dedupe clusters</h2>
		<p class="text-sm leading-6 text-slate-600">
			Review small groups of connected suggestions and leave obvious outliers unchecked.
		</p>
	</div>

	<AdminFlash error={form?.error} success={form?.success} />

	{#if candidate}
		<div class="flex flex-wrap items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
			<Badge variant="secondary">Cluster review</Badge>
			<span>{candidate.members.length} records</span>
			<span>{candidate.locked_pairs.length} locked edges</span>
			{#if lockExpiresAt}
				<span>Locked until {lockExpiresAt}</span>
			{/if}
		</div>

		<form method="POST" action="?/judge" use:enhance class="space-y-6">
			{#each candidate.members as member (member.entity.id)}
				<input type="hidden" name="entityId" value={member.entity.id} />
			{/each}
			{#each candidate.locked_pairs as pair (`${pair.left_id}::${pair.right_id}`)}
				<input type="hidden" name="lockedPair" value={`${pair.left_id}::${pair.right_id}`} />
			{/each}

			<div class="grid gap-6 xl:grid-cols-2">
				{#each candidate.members as member (member.entity.id)}
					<DedupeEntityCard
						entity={member.entity}
						score={member.score}
						selectable={true}
						selected={true}
						checkboxLabel="Merge this record"
					/>
				{/each}
			</div>

			<Card class="border-slate-200">
				<CardHeader>
					<CardTitle>Record judgement</CardTitle>
					<CardDescription>
						Judgements only apply to locked resolver suggestions where both endpoints are selected.
						Unchecked records stay unresolved.
					</CardDescription>
				</CardHeader>
				<CardContent class="flex flex-wrap gap-3">
					<Button type="submit" name="intent" value="match">Match</Button>
					<Button type="submit" name="intent" value="no_match" variant="secondary">
						No match
					</Button>
					<Button type="submit" name="intent" value="unsure" variant="outline">Unsure</Button>
					<Button type="submit" name="intent" value="skip" variant="secondary">Skip cluster</Button>
				</CardContent>
			</Card>
		</form>
	{:else}
		<Card class="border-emerald-200 bg-emerald-50">
			<CardHeader>
				<CardTitle class="text-emerald-950">No pending clusters</CardTitle>
				<CardDescription class="text-emerald-900">
					The clustered queue did not find any unresolved local groups.
				</CardDescription>
			</CardHeader>
		</Card>
	{/if}
</div>
