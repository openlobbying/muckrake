import type { Options } from "vis-network";

export const NETWORK_OPTIONS: Options = {
    nodes: {
        borderWidth: 1.5,
        borderWidthSelected: 3,
        shadow: {
            enabled: true,
            color: "rgba(0,0,0,0.05)",
            size: 3,
            x: 1,
            y: 1,
        },
    },
    edges: {
        smooth: {
            type: "continuous",
            enabled: true,
            roundness: 0.5,
        },
    },
    physics: {
        enabled: true,
        stabilization: {
            enabled: true,
            iterations: 1000,
            updateInterval: 50,
        },
        barnesHut: {
            gravitationalConstant: -10000,
            centralGravity: 0.1,
            springLength: 150,
            springConstant: 0.05,
            damping: 0.09,
            avoidOverlap: 1,
        },
    },
    interaction: {
        hover: true,
        tooltipDelay: 200,
        zoomView: true,
    },
};

export const EDGE_DEFAULT_CONFIG = {
    arrows: "to",
    font: {
        align: "middle",
        size: 9,
        color: "#4b5563",
        strokeWidth: 2,
        strokeColor: "#ffffff",
        multi: true,
    },
    color: {
        color: "#d1d5db",
        highlight: "#3b82f6",
        hover: "#9ca3af",
    },
    width: 1.5,
    hoverWidth: 3,
};
