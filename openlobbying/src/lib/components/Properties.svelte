<script lang="ts">
	import { getEntityRoute } from '$lib/util/routes';
	import { Badge } from '$lib/components/ui/badge';
	import { getPropertyLabel } from '$lib/presentation/property-profile';
	import { renderableValue } from '$lib/util/detail';

	interface Props {
		properties: Record<string, any[]>;
		type?: string;
		orderedKeys?: string[];
	}

	let { properties, type = '', orderedKeys }: Props = $props();

	const propertyEntries = $derived.by(() => {
		const keys = orderedKeys && orderedKeys.length > 0 ? orderedKeys : Object.keys(properties);
		return keys
			.filter((key) => Array.isArray(properties[key]) && properties[key].length > 0)
			.map((key) => [key, properties[key]] as const);
	});

</script>

<div class="overflow-hidden">
	<dl class="grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-4">
		{#each propertyEntries as [key, values]}
			<div class="sm:col-span-1">
				<dt class="text-sm font-medium text-gray-500 capitalize">{getPropertyLabel(type, key)}</dt>
			</div>
			<div class="sm:col-span-2">
				<dd class={`text-sm text-gray-900 ${key === 'summary' ? 'space-y-2' : 'flex flex-wrap gap-2'}`}>
					{#each values as value}
						{@const item = renderableValue(value, key)}
						{#if item.type === 'entity'}
							<a
								href={item.href}
								class="transition-colors hover:opacity-90"
							>
							<Badge variant="secondary">{item.text}</Badge>
							</a>
						{:else if item.type === 'url'}
							<a
								href={item.href}
								target="_blank"
								rel="noopener noreferrer"
								class="text-blue-700 underline decoration-blue-300 transition-colors hover:text-blue-900"
							>
								{item.text}
							</a>
						{:else if key === 'summary' && typeof value === 'string'}
							<div class="w-full rounded-md bg-gray-50 px-3 py-2 leading-relaxed text-gray-800">
								{value}
							</div>
						{:else}
							<Badge variant="secondary">{item.text}</Badge>
						{/if}
					{/each}
				</dd>
			</div>
		{/each}
	</dl>
</div>
