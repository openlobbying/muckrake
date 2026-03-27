## OpenLobbying frontend

The `openlobbying` directory contains a Svelte app that displays data from the `muckrake` database (`data/muckrake.db`). It uses a FastAPI backend (`src/api`).

You are able to use the Svelte MCP server, where you have access to comprehensive Svelte 5 and SvelteKit documentation. Here's how to use the available tools effectively:

### Available Svelte MCP Tools:

#### 1. list-sections

Use this FIRST to discover all available documentation sections. Returns a structured list with titles, use_cases, and paths.
When asked about Svelte or SvelteKit topics, ALWAYS use this tool at the start of the chat to find relevant sections.

#### 2. get-documentation

Retrieves full documentation content for specific sections. Accepts single or multiple sections.
After calling the list-sections tool, you MUST analyze the returned documentation sections (especially the use_cases field) and then use the get-documentation tool to fetch ALL documentation sections that are relevant for the user's task.

#### 3. svelte-autofixer

Analyzes Svelte code and returns issues and suggestions.
You MUST use this tool whenever writing Svelte code before sending it to the user. Keep calling it until no issues or suggestions are returned.

#### 4. playground-link

Generates a Svelte Playground link with the provided code.
After completing the code, ask the user if they want a playground link. Only call this tool after user confirmation and NEVER if code was written to files in their project.

#### Type Safety
- TypeScript strict mode is enabled
- Define interfaces for all data structures (see `src/lib/types.ts`)
- Use `Record<string, any[]>` for FtM entity properties
- Avoid `any` where possible; use specific types

#### Imports
- Use SvelteKit's `$lib` path alias for library imports
- Example:
  ```typescript
  import Properties from "$lib/components/Properties.svelte";
  import type { Entity } from "$lib/types";
  ```

#### Svelte 5 Runes
- Use `$props()` for component props
- Use `$derived` for computed values
- Use `$derived.by()` for complex derivations
- Example:
  ```svelte
  let { data } = $props();
  let entity = $derived(data.entity);
  ```

#### Data Fetching
- Use SvelteKit's `+page.ts` for data loading
- Fetch from FastAPI backend at runtime

### shadcn-svelte

Use `shadcn-svelte` components throughout the app for consistent styling. [Fetch the docs](https://www.shadcn-svelte.com/llms.txt) for usage examples.