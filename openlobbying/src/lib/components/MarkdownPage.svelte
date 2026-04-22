<script lang="ts">
	import type { Snippet } from 'svelte';
	let { title, description = '', updated = '', children } = $props<{
		title?: string;
		description?: string;
		updated?: string;
		children?: Snippet;
	}>();
</script>

<svelte:head>
	{#if title}
		<title>{title} - OpenLobbying</title>
		<meta property="og:title" content={`${title} - OpenLobbying`} />
	{/if}
	{#if description}
		<meta name="description" content={description} />
		<meta property="og:description" content={description} />
		<meta name="twitter:description" content={description} />
	{/if}
</svelte:head>

<article class="markdown-page">
	<header class="markdown-header">
		{#if title}
			<h1>{title}</h1>
		{/if}
		{#if description}
			<p class="lead">{description}</p>
		{/if}
		{#if updated}
			<p class="updated">Last updated: {updated}</p>
		{/if}
	</header>

	<div class="markdown-body">
		{#if children}
			{@render children()}
		{/if}
	</div>
</article>

<style>
	.markdown-page {
		max-width: 52rem;
		margin: 0 auto;
		padding: 3rem 1rem 4rem;
	}

	.markdown-header {
		margin-bottom: 2.5rem;
	}

	.markdown-header h1 {
		margin: 0;
		font-size: clamp(2.25rem, 4vw, 3.5rem);
		line-height: 1.05;
		letter-spacing: -0.03em;
		color: #0f172a;
	}

	.lead {
		margin: 1rem 0 0;
		font-size: 1.125rem;
		line-height: 1.75;
		color: #475569;
	}

	.updated {
		margin: 1rem 0 0;
		font-size: 0.95rem;
		color: #64748b;
	}

	.markdown-body :global(h2) {
		margin: 3rem 0 1rem;
		font-size: 1.75rem;
		line-height: 1.2;
		letter-spacing: -0.02em;
		color: #0f172a;
	}

	.markdown-body :global(h3) {
		margin: 2rem 0 0.75rem;
		font-size: 1.25rem;
		line-height: 1.3;
		color: #0f172a;
	}

	.markdown-body :global(p),
	.markdown-body :global(li) {
		font-size: 1rem;
		line-height: 1.8;
		color: #334155;
	}

	.markdown-body :global(p) {
		margin: 1rem 0;
	}

	.markdown-body :global(ul),
	.markdown-body :global(ol) {
		margin: 1rem 0;
		padding-left: 1.5rem;
	}

	.markdown-body :global(ul) {
		list-style: disc;
	}

	.markdown-body :global(ol) {
		list-style: decimal;
	}

	.markdown-body :global(li + li) {
		margin-top: 0.4rem;
	}

	.markdown-body :global(a) {
		color: #1d4ed8;
		text-decoration: underline;
		text-decoration-color: rgba(29, 78, 216, 0.35);
		text-underline-offset: 0.2em;
	}

	.markdown-body :global(a:hover) {
		text-decoration-color: currentColor;
	}

	.markdown-body :global(blockquote) {
		margin: 1.5rem 0;
		padding: 0.25rem 0 0.25rem 1rem;
		border-left: 3px solid #f59e0b;
		color: #475569;
	}

	.markdown-body :global(hr) {
		margin: 2rem 0;
		border: 0;
		border-top: 1px solid #e2e8f0;
	}
 </style>
