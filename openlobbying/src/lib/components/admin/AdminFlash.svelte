<script lang="ts">
	interface Props {
		error?: string;
		success?: string;
	}

	let { error, success }: Props = $props();
</script>

{#if error}
	<p class="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
		{error}
	</p>
{/if}

{#if success}
	<p class="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
		{success}
	</p>
{/if}
