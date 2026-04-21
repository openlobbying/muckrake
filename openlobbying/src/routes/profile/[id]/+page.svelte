<script lang="ts">
	import ProfileBox from "$lib/components/ProfileBox.svelte";
	import DatasetList from '$lib/components/DatasetList.svelte';
	import KeyDetails from "$lib/components/KeyDetails.svelte";
	import Relationships from "$lib/components/Relationships.svelte";
	import Timeline from "$lib/components/timeline/Timeline.svelte";
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { TextAlignJustify, Waypoints } from '@lucide/svelte';
	import type { Entity } from '$lib/types';
	import type { Component } from 'svelte';
	import {
		transformActivities,
		transformRelationships,
	} from "$lib/util/transformers";

	type ProfileTab = 'timeline' | 'network';

	let { data }: { data: { entity: Promise<Entity> } } = $props();
	let activeTab = $state<ProfileTab>('timeline');
	let NetworkGraphComponent = $state<Component<{ entity: Entity }> | null>(null);
	let networkComponentLoading = $state(false);
	let networkComponentError = $state<string | null>(null);

	async function openTab(tab: ProfileTab, hasNetwork: boolean) {
		activeTab = tab;
		if (tab !== 'network' || !hasNetwork || NetworkGraphComponent || networkComponentLoading) {
			return;
		}

		networkComponentLoading = true;
		networkComponentError = null;
		try {
			const module = await import('$lib/components/NetworkGraph.svelte');
			NetworkGraphComponent = module.default;
		} catch (error) {
			networkComponentError = error instanceof Error
				? error.message
				: 'Failed to load network graph.';
		} finally {
			networkComponentLoading = false;
		}
	}
</script>

<svelte:head>
	{#await data.entity}
		<title>Profile - OpenLobbying</title>
	{:then entity}
		<title>{entity.caption ?? entity.canonical_id} - OpenLobbying</title>
	{:catch}
		<title>Profile - OpenLobbying</title>
	{/await}
</svelte:head>

{#snippet EmptyState(message: string)}
	<Card>
		<CardContent>
			<p class="text-sm text-slate-600">{message}</p>
		</CardContent>
	</Card>
{/snippet}

<div class="max-w-7xl mx-auto px-4 py-8">
	{#await data.entity}
		<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
			<div class="lg:col-span-1 space-y-6">
				<Card>
					<CardContent class="space-y-4 p-6">
						<Skeleton class="h-24 w-24 rounded-full" />
						<Skeleton class="h-6 w-3/4 rounded" />
						<Skeleton class="h-4 w-1/2 rounded" />
					</CardContent>
				</Card>
				<Card>
					<CardContent class="space-y-3 p-6">
						<Skeleton class="h-5 w-32 rounded" />
						<Skeleton class="h-4 w-full rounded" />
						<Skeleton class="h-4 w-5/6 rounded" />
						<Skeleton class="h-4 w-2/3 rounded" />
					</CardContent>
				</Card>
			</div>

			<div class="lg:col-span-2 space-y-6">
				<div class="inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
					<Skeleton class="h-8 w-24 rounded-md" />
					<Skeleton class="ml-1 h-8 w-24 rounded-md" />
				</div>
				<Card>
					<CardContent class="space-y-4 p-6">
						<Skeleton class="h-5 w-2/5 rounded" />
						<Skeleton class="h-4 w-full rounded" />
						<Skeleton class="h-4 w-11/12 rounded" />
						<Skeleton class="h-4 w-3/4 rounded" />
					</CardContent>
				</Card>
			</div>
		</div>
	{:then entity}
		{@const activities = transformActivities(entity)}
		{@const relationships = transformRelationships(entity)}
		{@const hasNetwork = Boolean(entity.adjacent && Object.keys(entity.adjacent).length > 0)}
		{@const hasActivities = activities.length > 0}

		<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
			<div class="lg:col-span-1 space-y-6">
				<ProfileBox {entity} />
				<KeyDetails {entity} />

				{#if relationships.length > 0}
					<Relationships {relationships} />
				{/if}

				{#if entity.datasets && entity.datasets.length > 0}
					<Card>
						<CardHeader>
							<CardTitle>Datasets</CardTitle>
						</CardHeader>
						<CardContent>
							<DatasetList datasets={entity.datasets} variant="stacked" />
						</CardContent>
					</Card>
				{/if}
			</div>

			<div class="lg:col-span-2">
				<div class="mb-6 flex flex-wrap gap-2">
					<Button
						size="sm"
						variant={activeTab === 'timeline' ? 'default' : 'outline'}
						onclick={() => openTab('timeline', hasNetwork)}
					>
						<TextAlignJustify class="mr-1.5 h-4 w-4" />
						Activity
					</Button>
					<Button
						size="sm"
						variant={activeTab === 'network' ? 'default' : 'outline'}
						onclick={() => openTab('network', hasNetwork)}
						disabled={!hasNetwork}
					>
						<Waypoints class="mr-1.5 h-4 w-4" />
						Network
					</Button>
				</div>

				{#if activeTab === 'timeline'}
					{#if hasActivities}
						<Timeline {activities} currentEntityId={entity.id} title="" />
					{:else}
						{@render EmptyState('No activity available for this profile.')}
					{/if}
				{:else}
					{#if hasNetwork}
						<Card class="overflow-hidden py-0 gap-0">
							<CardContent class="p-0">
								{#if networkComponentLoading}
									<div class="w-full aspect-square min-h-[280px] max-h-[700px] sm:min-h-[320px]">
										<Skeleton class="h-full w-full rounded-none" />
									</div>
								{:else if networkComponentError}
									<div class="flex min-h-[220px] items-center justify-center px-6 text-center">
										<p class="text-sm text-slate-600">{networkComponentError}</p>
									</div>
								{:else if NetworkGraphComponent}
									{#key entity.id}
										<NetworkGraphComponent {entity} />
									{/key}
								{/if}
							</CardContent>
						</Card>
					{:else}
						{@render EmptyState('No network data available for this profile.')}
					{/if}
				{/if}
			</div>
		</div>
	{:catch}
		<Card>
			<CardContent>
				<p class="text-sm text-slate-600">Could not fetch profile.</p>
			</CardContent>
		</Card>
	{/await}
</div>
