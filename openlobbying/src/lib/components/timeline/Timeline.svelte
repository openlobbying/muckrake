<script lang="ts">
	import TimelineItem from './TimelineItem.svelte';
	import { allTypes } from './registry';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';

	interface Props {
		activities: any[];
		currentEntityId?: string;
		title?: string;
	}

	let { activities = [], currentEntityId = '', title = 'Activity Timeline' }: Props = $props();

	const activityTypes = $derived([...new Set(activities.map((a) => a.type))]);
	const availableFilters = $derived(allTypes().filter((t) => activityTypes.includes(t.key)));

	let selectedFilter = $state<string | null>(null);
	let showCount = $state(20);
	let previousFilter = $state<string | null>(null);

	$effect(() => {
		if (selectedFilter !== previousFilter) {
			previousFilter = selectedFilter;
			showCount = 20;
		}
	});

	const filteredActivities = $derived(
		selectedFilter ? activities.filter((a) => a.type === selectedFilter) : activities
	);

	const displayedActivities = $derived(filteredActivities.slice(0, showCount));
	const hasMore = $derived(displayedActivities.length < filteredActivities.length);
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
			{#each displayedActivities as activity (activity.id)}
				<TimelineItem {activity} {currentEntityId} />
			{/each}
		</div>

		{#if hasMore}
			<div class="text-center">
				<Button
					onclick={() => (showCount += 10)}
					variant="outline"
					class="rounded-full"
				>
					Show more activities
				</Button>
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
