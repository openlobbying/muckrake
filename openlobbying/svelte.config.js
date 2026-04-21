import adapter from '@sveltejs/adapter-node';
import { mdsvex } from 'mdsvex';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const rootDir = fileURLToPath(new URL('.', import.meta.url));

const mdsvexConfig = {
	extensions: ['.svx'],
	layout: path.resolve(rootDir, 'src/lib/components/MarkdownPage.svelte')
};

/** @type {import('@sveltejs/kit').Config} */
const config = {
	extensions: ['.svelte', '.svx'],
	// Consult https://svelte.dev/docs/kit/integrations
	// for more information about preprocessors
	preprocess: [vitePreprocess(), mdsvex(mdsvexConfig)],

	kit: {
		adapter: adapter()
	}
};

export default config;
