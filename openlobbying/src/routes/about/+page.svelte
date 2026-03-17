<script lang="ts">
	import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '$lib/components/ui/card';
</script>

<svelte:head>
	<title>About - OpenLobbying</title>
</svelte:head>

<div class="max-w-4xl mx-auto px-4 py-12">
	<header class="mb-8">
		<h1 class="text-4xl font-bold text-gray-900">About OpenLobbying</h1>
		<p class="mt-3 text-lg text-gray-600">
			OpenLobbying is an initiative to collect, standardise and match lobbying data in the UK. It is developed by <a href="https://nicu.md" target="_blank" rel="noreferrer" class="text-blue-700 hover:underline">Nicu Calcea</a> and Dr. Emily Clough.
		</p>
	</header>

	<div class="embed-container mb-8">
		<iframe
			src="https://www.youtube.com/embed/rU983OXuVUU"
			frameborder="0"
			allowfullscreen
			title="OpenLobbying video"
		></iframe>
	</div>

	<Card class="mb-8 border-amber-200 bg-amber-50">
		<CardHeader>
			<CardTitle class="text-amber-900">Development Notice</CardTitle>
		</CardHeader>
		<CardContent>
			<p class="text-amber-800">
			This project is in active development. Data coverage, matching quality, and site features are still improving and may change without notice.
			</p>
		</CardContent>
	</Card>

	<Card class="mb-8 border-blue-200 bg-blue-50">
		<CardHeader>
			<CardTitle class="text-blue-900">Corrections and challenges</CardTitle>
			<CardDescription>
				If you believe a profile or linked record is inaccurate, you can ask us to review it.
			</CardDescription>
		</CardHeader>
		<CardContent class="space-y-4 text-blue-950">
			<p>
				Send correction requests to
				<a href="mailto:mail@openlobbying.org" class="text-blue-700 hover:underline">mail@openlobbying.org</a>
				with the subject line: <span class="font-medium">Correction request</span>.
			</p>
			<p>Please include:</p>
			<ul class="list-disc space-y-1 pl-6">
				<li>the profile URL(s) or statement URL(s) in question;</li>
				<li>what is wrong and what should be changed;</li>
				<li>source links or evidence supporting the correction.</li>
			</ul>
			<p>
				We aim to acknowledge requests within 5 working days and in all cases within 30 days, and to
				resolve straightforward corrections as quickly as possible.
			</p>
		</CardContent>
	</Card>

	<Card>
		<CardHeader>
			<CardTitle>Contact</CardTitle>
			<CardDescription>
			If you have any questions, feedback or are interested in working together, please get in touch!
			</CardDescription>
		</CardHeader>
		<CardContent>
		<ul class="mt-4 space-y-2 text-gray-700">
			<li>
				<span class="font-medium text-gray-900">Email:</span>
				<a href="mailto:mail@openlobbying.org" class="text-blue-700 hover:underline"
					>mail@openlobbying.org</a
				>
			</li>
			<li>
				<span class="font-medium text-gray-900">LinkedIn:</span>
				<a
					href="https://www.linkedin.com/in/nicucalcea/"
					target="_blank"
					rel="noreferrer"
					class="text-blue-700 hover:underline"
					>linkedin.com/in/nicucalcea</a
				>
			</li>
		</ul>
		</CardContent>
	</Card>

</div>

<style>
	.embed-container {
		position: relative;
		padding-bottom: 56.25%;
		height: 0;
		overflow: hidden;
		max-width: 100%;
	}

	.embed-container iframe,
	.embed-container object,
	.embed-container embed {
		position: absolute;
		top: 0;
		left: 0;
		width: 100%;
		height: 100%;
	}
</style>
