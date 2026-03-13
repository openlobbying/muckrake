<script lang="ts">
    import { onDestroy } from "svelte";
    import { goto } from "$app/navigation";
    import { Network } from "vis-network";
    import { DataSet } from "vis-data";
    import type { Edge, Node } from "vis-network";
    import type { Entity, GraphData } from "$lib/types";
	import {
		NETWORK_OPTIONS,
		EDGE_DEFAULT_CONFIG,
	} from "$lib/util/graph_config";

	import { getIconUrl } from "$lib/util/entities";
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';

    let { entity }: { entity: Entity } = $props();

    let container: HTMLElement;
    let network: Network | undefined;
    let loading = $state(true);
    let error = $state<string | null>(null);

    const API_BASE = "/api";
    const MAX_LABEL_LINE_LENGTH = 30;

    function wrapLabel(label: string, maxLineLength = MAX_LABEL_LINE_LENGTH): string {
        const words = label.split(/\s+/).filter(Boolean);
        const lines: string[] = [];
        let currentLine = "";

        for (const word of words) {
            if (!currentLine) {
                currentLine = word;
                continue;
            }

            if (`${currentLine} ${word}`.length <= maxLineLength) {
                currentLine = `${currentLine} ${word}`;
                continue;
            }

            lines.push(currentLine);
            currentLine = word;
        }

        if (currentLine) {
            lines.push(currentLine);
        }

        return lines.join("\n");
    }

    async function fetchGraphData(id: string): Promise<GraphData> {
        const response = await fetch(`${API_BASE}/entities/${id}/graph`);
        if (!response.ok) {
            throw new Error("Failed to fetch graph data");
        }
        return response.json();
    }

    function initNetwork(data: GraphData, processedNodes: Node[]) {
        if (!container) return;

        const nodes = new DataSet<Node>(processedNodes);
        const edges = new DataSet<Edge>(
            data.edges.map((e) => ({
                ...EDGE_DEFAULT_CONFIG,
                from: e.from,
                to: e.to,
                label: e.label,
            })),
        );

        if (network) {
            network.destroy();
        }

        network = new Network(container, { nodes, edges }, NETWORK_OPTIONS);

        network.on("stabilizationIterationsDone", () => {
            network?.setOptions({ physics: { enabled: false } });
            loading = false;
        });

        network.on("doubleClick", (params) => {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                if (nodeId !== entity.id) {
                    goto(`/profile/${nodeId}`);
                }
            }
        });
    }

    $effect(() => {
        if (entity?.id) {
            loading = true;
            error = null;
            fetchGraphData(entity.id)
                .then(async (data) => {
                    const processedNodes = await Promise.all(
                        data.nodes.map(async (n) => {
                            const isCurrent = n.id === entity.id;
                            const iconUrl = await getIconUrl(n.id, n.schema);
                            return {
                                id: n.id,
                                label: wrapLabel(n.caption),
                                title: `${n.schema}: ${n.caption}`,
                                shape: "image",
                                image: iconUrl,
                                size: isCurrent ? 30 : 20,
                                font: {
                                    size: isCurrent ? 14 : 11,
                                    color: "#374151",
                                    strokeWidth: 3,
                                    strokeColor: "#ffffff",
                                },
                            };
                        }),
                    );
                    initNetwork(data, processedNodes);
                })
                .catch((err) => {
                    console.error(err);
                    error = err.message;
                    loading = false;
                });
        }
    });

    onDestroy(() => {
        network?.destroy();
    });
</script>

<div class="graph-container-wrapper">
	{#if loading}
		<div class="overlay">
			<Skeleton class="h-full w-full rounded-none" />
		</div>
	{/if}

    {#if error}
        <div class="overlay error">
            <span class="text-sm font-medium">{error}</span>
        </div>
    {/if}

    <div bind:this={container} class="graph-canvas"></div>
</div>

<style>
    .graph-container-wrapper {
        position: relative;
        width: 100%;
        aspect-ratio: 1 / 1;
        min-height: 320px;
        max-height: 700px;
        background: radial-gradient(circle at center, #ffffff 0%, #fafafa 100%);
        border-radius: 0.5rem;
        overflow: hidden;
    }

    @media (max-width: 640px) {
        .graph-container-wrapper {
            min-height: 280px;
        }
    }

    .graph-canvas {
        width: 100%;
        height: 100%;
    }

    .overlay {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(255, 255, 255, 0.7);
        z-index: 10;
        pointer-events: none;
    }

    .error {
        color: #ef4444;
    }

    :global(div.vis-network-tooltip) {
        background-color: white !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 0.375rem !important;
        padding: 0.6rem !important;
        font-family: ui-sans-serif, system-ui !important;
        font-size: 0.75rem !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1) !important;
    }
</style>
