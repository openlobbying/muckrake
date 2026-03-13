import {
    MapPin,
    Phone,
    Mail,
    FileText,
    Calendar,
    Globe,
    IdCard,
    Hash,
    Info,
} from "@lucide/svelte";
import type { Entity } from "../types";
import { formatLabel } from "./detail";

export const SPECIAL_CONFIG = [
    {
        label: "Name",
        keys: ["name", "alias", "weakAlias", "previousName"],
        icon: IdCard,
    },
    {
        label: "Summary",
        keys: ["summary"],
        icon: FileText,
    },
    {
        label: "Registration Number",
        keys: ["registrationNumber", "innCode", "vatCode"],
        icon: Hash,
    },
    {
        label: "Address",
        keys: ["address", "addressEntity"],
        icon: MapPin,
    },
    {
        label: "Phone",
        keys: ["phone"],
        icon: Phone,
    },
    {
        label: "Email",
        keys: ["email"],
        icon: Mail,
    },
    {
        label: "Website",
        keys: ["website"],
        icon: Globe,
        isLink: true,
    },
    {
        label: "Established",
        keys: ["incorporationDate", "birthDate", "startDate"],
        icon: Calendar,
    },
];

export const CONSUMED_KEYS = new Set([
    ...SPECIAL_CONFIG.flatMap((c) => c.keys),
    // "topics",
    // "country",
    // "jurisdiction",
]);

export interface KeyDetail {
    label: string;
    values: string[];
    icon: any;
    isLink?: boolean;
    linkUrl?: string;
}

/**
 * Checks if a registration number is a GB Companies House number
 * and returns the appropriate URL if it is.
 */
export function getCompaniesHouseUrl(registrationNumber: string): string | null {
    if (registrationNumber.startsWith("GB-COH-")) {
        const companyNumber = registrationNumber.substring(7); // Remove "GB-COH-" prefix
        return `https://find-and-update.company-information.service.gov.uk/company/${companyNumber}`;
    }
    return null;
}

export function getKeyDetails(entity: Entity): KeyDetail[] {
    const details = SPECIAL_CONFIG.map((config) => {
        const values = config.keys.flatMap((key) => {
            const val = entity.properties[key];
            if (!val) return [];
            return val.map((v: any) =>
                typeof v === "object" ? v.caption : v,
            );
        });
        
        // Check if this is a registration number field and if any value is a GB-COH number
        let linkUrl: string | undefined;
        if (config.label === "Registration Number" && values.length > 0) {
            // Check the first registration number for GB-COH prefix
            linkUrl = getCompaniesHouseUrl(values[0]) || undefined;
        }
        
        return { ...config, values, linkUrl };
    }).filter((d) => d.values.length > 0);

    const otherDetails = Object.entries(entity.properties)
        .filter(([key]) => !CONSUMED_KEYS.has(key))
        .map(([key, values]) => ({
            label: formatLabel(key),
            values: values.map((v: any) =>
                typeof v === "object" ? v.caption : v,
            ),
            icon: Info,
            isLink: false,
        }));

    return [...details, ...otherDetails];
}
