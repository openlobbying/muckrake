<script lang="ts">
	import { ChevronRight } from "@lucide/svelte";
	import { getEntityRoute } from "$lib/util/routes";
	import { relationshipIcons } from "$lib/util/entities";
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';

	let { relationships = [] } = $props();

	let expandedGroups = $state<Record<string, boolean>>({});

	function getIcon(type: string) {
		// @ts-ignore
		return relationshipIcons[type] || relationshipIcons.others;
	}

	function getLabel(type: string) {
		if (type === "other links") return "Other links";
		return type;
	}

	function toggleGroup(type: string) {
		expandedGroups[type] = !expandedGroups[type];
	}
</script>

<Card>
	<CardHeader>
		<CardTitle>Relationships</CardTitle>
	</CardHeader>
	<CardContent>
	<div class="space-y-4">
		{#each relationships as group (group.type)}
			{@const Icon = getIcon(group.type)}
			{@const items = expandedGroups[group.type]
				? group.items
				: group.items.slice(0, 10)}
			<div class="border-b border-gray-100 last:border-0 pb-4 last:pb-0">
				<div class="flex items-center justify-between mb-3">
					<div class="flex items-center space-x-2">
						<Icon class="w-4 h-4 text-gray-500" />
						<h3
							class="text-sm font-semibold text-gray-700 capitalize"
						>
							{getLabel(group.type)}
						</h3>
						<Badge variant="secondary">{group.items.length}</Badge>
					</div>
				</div>
				<div class="space-y-2">
					{#each items as item, itemIndex (`${group.type}-${item.id}-${item.schema}-${item.role || 'none'}-${itemIndex}`)}
						<div
							class="flex items-center justify-between rounded-lg hover:bg-gray-50 transition-colors group"
						>
							<a
								href={getEntityRoute(item.id, item.schema)}
								class="flex-1 min-w-0 p-2 flex items-center justify-between"
							>
								<div class="min-w-0">
									<p
										class="text-sm font-medium text-gray-900 truncate"
									>
										{item.name}
									</p>
									{#if item.role}
										<p
											class="text-xs text-gray-500 truncate"
										>
											{item.role}
										</p>
									{/if}
									{#if item.activePeriod}
										<p
											class="text-xs text-gray-400 truncate"
										>
											{item.activePeriod}
										</p>
									{/if}
								</div>
								<ChevronRight
									class="w-4 h-4 text-gray-400 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity ml-2"
								/>
							</a>
						</div>
					{/each}
				</div>
				{#if group.items.length > 10}
					<div class="mt-2 pt-2 border-t border-gray-50">
						<button
							onclick={() => toggleGroup(group.type)}
							type="button"
							class="text-sm text-blue-600 hover:text-blue-800 inline-flex items-center"
						>
							{#if expandedGroups[group.type]}
								Collapse
								<ChevronRight class="w-4 h-4 ml-1 -rotate-90" />
							{:else}
								Show all {group.items.length}
								<ChevronRight class="w-4 h-4 ml-1 rotate-90" />
							{/if}
						</button>
					</div>
				{/if}
			</div>
		{/each}
	</div>
	</CardContent>
</Card>
