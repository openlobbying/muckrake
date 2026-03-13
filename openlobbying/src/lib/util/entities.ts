import { Building2, Users, Landmark, User, UserCircle, Briefcase } from '@lucide/svelte';
import { mount, unmount } from 'svelte';

export const schemaColors: Record<string, string> = {
    Person: '#fb923c', // orange-400
    Company: '#60a5fa', // blue-400
    Organization: '#34d399', // emerald-400
    PublicBody: '#f87171', // red-400
    LegalEntity: '#94a3b8', // slate-400
};

export const entityIcons: Record<string, any> = {
    Company: Building2,
    Organization: Users,
    PublicBody: Landmark,
    Person: User,
    LegalEntity: Building2
};

export const relationshipIcons: Record<string, any> = {
    lobbyists: UserCircle,
    clients: Users,
    employers: Briefcase,
    employees: Users,
    organizations: Briefcase,
    members: UserCircle,
    others: Users
};

export const entityCustomAssets: Record<string, { icon?: string, color?: string }> = {
    'GB-PARTY-15': {
        icon: '/custom-icons/labour.svg',
        color: '#E4003B' // https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Politics_of_the_United_Kingdom/Index_of_United_Kingdom_political_parties_meta_attributes
    },
    'GB-PARTY-4': {
        icon: '/custom-icons/conservative.svg',
        color: '#0087DC'
    },
    'GB-PARL-1': {
        icon: '/custom-icons/commons.png',
        color: '#006548'
    }
};

/**
 * Returns the assets (color and icon) for a given entity, checking for custom overrides first.
 */
export function getEntityAssets(id: string, schema: string) {
    const custom = entityCustomAssets[id];
    const baseColor = schemaColors[schema] || "#9ca3af";
    const baseIcon = entityIcons[schema] || Building2;

    return {
        color: custom?.color || baseColor,
        icon: custom?.icon || baseIcon,
        isCustomIcon: !!custom?.icon
    };
}

/**
 * Dynamically generates an SVG Data URL for a Lucide icon component.
 * This should only be called in a browser environment (DOM available).
 */
export async function getIconUrl(id: string, schema: string): Promise<string> {
    if (typeof document === 'undefined') return '';
    
    const { color, icon, isCustomIcon } = getEntityAssets(id, schema);

    if (isCustomIcon && typeof icon === 'string') {
        // Load the image and draw it onto a canvas with the standard circle styling
        return new Promise((resolve) => {
            const img = new Image();
            img.crossOrigin = "Anonymous";
            img.onload = () => {
                // Use a higher resolution canvas (4x) to prevent pixelation on zoom/high-DPI screens
                const scale = 4;
                const size = 32 * scale; // 128px
                const center = 16 * scale;
                const radius = 15 * scale;
                const lineWidth = 2 * scale;
                const imgParsedSize = 18 * scale; // Slightly larger icon inside circle
                const imgOffset = (size - imgParsedSize) / 2;

                const canvas = document.createElement('canvas');
                canvas.width = size;
                canvas.height = size;
                const ctx = canvas.getContext('2d');
                if (!ctx) {
                    resolve(icon); // Fallback to raw URL
                    return;
                }

                // Circle styling
                ctx.beginPath();
                ctx.arc(center, center, radius, 0, 2 * Math.PI);
                ctx.fillStyle = 'white';
                ctx.fill();
                
                // Stroke styling
                ctx.lineWidth = lineWidth;
                ctx.strokeStyle = color;
                ctx.stroke();

                // Draw the image centered
                ctx.drawImage(img, imgOffset, imgOffset, imgParsedSize, imgParsedSize);

                resolve(canvas.toDataURL());
            };
            img.onerror = () => resolve(icon); // Fallback
            img.src = icon;
        });
    }

    const IconComponent = icon as any;
    
    // Create a temporary container for rendering
    const div = document.createElement('div');
    
    // Render the Svelte component into the container
    const app = mount(IconComponent, {
        target: div,
        props: {
            color: color,
            size: 16, // Smaller icon to fit inside circle
            strokeWidth: 2
        }
    });

    // Extract the SVG path for the icon
    const svgElement = div.querySelector('svg');
    const iconContent = svgElement ? svgElement.innerHTML : '';
    
    // Cleanup
    unmount(app);

    if (!iconContent) return '';

    // Create a new SVG that has a solid circular background
    // This prevents edge lines from being visible behind the icon
    const decoratedSvg = `
        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
            <circle cx="16" cy="16" r="15" fill="white" stroke="${color}" stroke-width="2" />
            <g transform="translate(8, 8)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    ${iconContent}
                </svg>
            </g>
        </svg>
    `;
    
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(decoratedSvg)}`;
}


