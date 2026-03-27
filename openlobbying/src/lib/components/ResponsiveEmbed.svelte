<script lang="ts">
	let { src, title } = $props<{ src: string; title: string }>();
</script>

<div class="embed-frame">
	<iframe {src} {title} frameborder="0" allowfullscreen></iframe>
</div>

<style>
	.embed-frame {
		position: relative;
		margin: 2rem 0;
		aspect-ratio: 16 / 9;
		overflow: hidden;
		border-radius: 1rem;
		background: #0f172a;
		box-shadow: 0 18px 45px rgba(15, 23, 42, 0.18);
	}

	.embed-frame iframe {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		border: 0;
	}
</style>
