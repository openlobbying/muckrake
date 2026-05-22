<script lang="ts">
	import TimelineItem from './TimelineItem.svelte';
	import { allTypes } from './registry';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import type { TimelineItem as TimelineActivity } from '$lib/types';

	interface Props {
		activities: TimelineActivity[];
		currentEntityId?: string;
		title?: string;
		hasMore?: boolean;
		loadingMore?: boolean;
		loadMoreError?: string | null;
		onLoadMore?: () => void;
	}

	let {
		activities = [],
		currentEntityId = '',
		title = 'Activity Timeline',
		hasMore = false,
		loadingMore = false,
		loadMoreError = null,
		onLoadMore,
	}: Props = $props();

	const activityTypes = $derived([...new Set(activities.map((a) => a.type))]);
	const availableFilters = $derived(allTypes().filter((t) => activityTypes.includes(t.key)));

	let selectedFilter = $state<string | null>(null);

	const filteredActivities = $derived(
		selectedFilter ? activities.filter((a) => a.type === selectedFilter) : activities
	);
	const canLoadMore = $derived(hasMore && typeof onLoadMore === 'function');
</script>

<Card class="bg-gray-50/50 py-0 gap-0">
	{#if title}
		<CardHeader>
			<CardTitle>{title}</CardTitle>
		</CardHeader>
	{/if}
	<CardContent class={title ? 'pb-6' : 'pt-6 pb-6'}>
	{#if availableFilters.length > 1}
		<div class="mb-4 flex flex-wrap gap-2">
				<Button
					onclick={() => (selectedFilter = null)}
					size="sm"
					variant={selectedFilter === null ? 'default' : 'outline'}
				>
					All
				</Button>
				{#each availableFilters as type (type.key)}
					<Button
						onclick={() => (selectedFilter = type.key)}
						size="sm"
						variant={selectedFilter === type.key ? 'default' : 'outline'}
					>
						{type.label || type.key}
					</Button>
				{/each}
		</div>
	{/if}

	<div class="relative">
		<!-- Vertical Line -->
		<div class="absolute left-6 top-0 bottom-0 w-0.5 bg-gray-200"></div>

		<div class="space-y-2">
			{#each filteredActivities as activity (activity.id)}
				<TimelineItem {activity} {currentEntityId} />
			{/each}
		</div>

		{#if canLoadMore}
			<div class="text-center">
				<Button
					onclick={() => onLoadMore?.()}
					variant="outline"
					class="rounded-full"
					disabled={loadingMore}
				>
					{loadingMore ? 'Loading activities...' : 'Show more activities'}
				</Button>
			</div>
		{/if}

		{#if loadMoreError}
			<div class="pt-3 text-center">
				<p class="text-sm text-red-600">{loadMoreError}</p>
			</div>
		{/if}

		{#if filteredActivities.length === 0}
			<div class="text-center py-12">
				<p class="text-gray-500">No activities found.</p>
			</div>
		{/if}
	</div>
	</CardContent>
</Card>
