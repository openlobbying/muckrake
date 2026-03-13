## OpenLobbying frontend

The `openlobbying` directory contains a Svelte app that displays data from the `muckrake` database (`data/muckrake.db`). It uses a FastAPI backend (`src/api`).

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