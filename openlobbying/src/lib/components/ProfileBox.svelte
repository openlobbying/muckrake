<script lang="ts">
	import { getEntityAssets } from "$lib/util/entities";
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';

	let { entity } = $props();

	const assets = $derived(getEntityAssets(entity.id, entity.schema));
	const Icon = $derived(typeof assets.icon !== "string" ? assets.icon : null);
	const iconUrl = $derived(
		typeof assets.icon === "string" ? assets.icon : null,
	);

	const name = $derived(entity.caption || entity.properties.name?.[0]);
	const industry = $derived(
		entity.properties.sector?.[0] || entity.properties.mainBusiness?.[0],
	);
</script>

<Card>
	<CardContent>
	<div class="flex items-start space-x-4">
		<div class="flex-shrink-0">
			<div
				class="w-16 h-16 rounded-lg flex items-center justify-center"
				style="background-color: {assets.color}20"
			>
				{#if Icon}
					<Icon class="w-8 h-8" style="color: {assets.color}" />
				{:else if iconUrl}
					<img
						src={iconUrl}
						alt={name}
						class="w-10 h-10 object-contain"
					/>
				{/if}
			</div>
		</div>
		<div class="flex-1 min-w-0">
			<h1 class="text-2xl font-bold text-gray-900 mb-1 break-words">
				{name}
			</h1>
			<p class="text-sm text-gray-600 capitalize">{entity.schema}</p>
			{#if industry}
				<div class="mt-2">
				<Badge variant="secondary">
					{industry}
				</Badge>
				</div>
			{/if}
		</div>
	</div>
	</CardContent>
</Card>
