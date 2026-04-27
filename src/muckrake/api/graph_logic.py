from typing import Any, Dict, List
from followthemoney.types import registry
from muckrake.api.serialization import is_actor

def format_currency(amount: float) -> str:
    if amount >= 1_000_000:
        return f"£{amount / 1_000_000:.1f}m"
    if amount >= 1_000:
        return f"£{amount / 1_000:.1f}k"
    return f"£{amount:.0f}"

def get_entity_graph_data(view, entity_id: str) -> Dict[str, Any]:
    """Get aggregated 1st-degree connections for graph visualization."""
    root = view.get_entity(entity_id)
    if root is None:
        return {"nodes": [], "edges": []}

    # Map target_id -> list of (relationship, is_outbound)
    connections: Dict[str, List[tuple[Any, bool]]] = {}
    
    # Map target_id -> simplified node info for visualization
    node_info: Dict[str, Dict[str, str]] = {
        entity_id: {"id": root.id, "caption": root.caption, "schema": root.schema.name}
    }

    def is_root_source_of_relationship(rel: Any) -> bool:
        sc = rel.schema
        def root_is_in_prop(prop_name):
            if prop_name in sc.properties:
                return entity_id in rel.get(prop_name)
            return False

        if sc.is_a("Payment"):          return root_is_in_prop("payer")
        if sc.is_a("Representation"):   return root_is_in_prop("agent")
        if sc.is_a("Employment"):       return root_is_in_prop("employee")
        if sc.is_a("Membership"):       return root_is_in_prop("member")
        if sc.is_a("Ownership"):        return root_is_in_prop("owner")
        if sc.is_a("Directorship"):     return root_is_in_prop("director")
        if sc.is_a("Interest"):         return root_is_in_prop("holder")
        if sc.is_a("Event"):            return root_is_in_prop("involved")
        
        return True

    def add_node(target_id: str):
        if target_id not in node_info:
            ent = view.get_entity(target_id)
            if ent and is_actor(ent.schema.name):
                node_info[target_id] = {
                    "id": ent.id, 
                    "caption": ent.caption, 
                    "schema": ent.schema.name
                }
        return target_id in node_info

    def add_connection(target: str, data: Any, outbound: bool):
        if target not in connections:
            connections[target] = []
        connections[target].append((data, outbound))

    for prop, adj in view.get_adjacent(root):
        if is_actor(adj.schema.name):
            if add_node(adj.id):
                outbound = prop.schema.is_a(root.schema.name)
                add_connection(adj.id, prop.label, outbound)
        else:
            targets = []
            if adj.schema.is_a("Event"):
                for org_id in adj.get("organizer"):
                    if org_id != entity_id:
                        targets.append(org_id)
            else:
                for p_prop in adj.schema.properties.values():
                    if p_prop.type == registry.entity:
                        for val in adj.get(p_prop):
                            if val != entity_id:
                                targets.append(val)
            
            is_outbound = is_root_source_of_relationship(adj)
            for target_id in targets:
                if add_node(target_id):
                    add_connection(target_id, adj, is_outbound)

    edges = []
    for target_id, rel_data in connections.items():
        if not rel_data: continue
            
        summaries = []
        outbound_weight = 0
        property_labels = sorted({r for r, side in rel_data if isinstance(r, str)})
        entity_rels = [r for r, side in rel_data if not isinstance(r, str)]
        
        for _, side in rel_data:
            outbound_weight += 1 if side else -1

        summaries.extend(property_labels)
        by_schema: Dict[str, List[Any]] = {}
        for r in entity_rels:
            by_schema.setdefault(r.schema.name, []).append(r)
            
        for schema_name, schema_rels in by_schema.items():
            count = len(schema_rels)
            if schema_name in {"Payment", "Donation", "Gift", "Hospitality"}:
                total = sum(float(amt) for r in schema_rels for amt in r.get("amount") if amt)
                if schema_name == "Donation":
                    label = f"Donated {format_currency(total)}" if total > 0 else "Donation"
                elif schema_name == "Gift":
                    label = f"Gifted {format_currency(total)}" if total > 0 else "Gift"
                elif schema_name == "Hospitality":
                    label = f"Hospitality {format_currency(total)}" if total > 0 else "Hospitality"
                else:
                    label = f"Donated {format_currency(total)}" if total > 0 else "Payment"
                summaries.append(f"{label} ({count}x)" if count > 1 else label)
            elif schema_name in {"Event", "Meeting"}:
                if schema_name == "Meeting":
                    label = "Meeting"
                    summaries.append(f"{label} ({count}x)" if count > 1 else label)
                    continue
                meeting_count = sum(1 for r in schema_rels if any("Meeting" in k for k in r.get("keywords")))
                evidence_count = sum(1 for r in schema_rels if any("Evidence" in k for k in r.get("keywords")))
                other_count = count - meeting_count - evidence_count
                
                if meeting_count > 0:
                    label = "Meeting"
                    summaries.append(f"{label} ({meeting_count}x)" if meeting_count > 1 else label)
                if evidence_count > 0:
                    label = "Evidence"
                    summaries.append(f"{label} ({evidence_count}x)" if evidence_count > 1 else label)
                if other_count > 0:
                    label = "Event"
                    summaries.append(f"{label} ({other_count}x)" if other_count > 1 else label)
            else:
                label = schema_rels[0].schema.label
                summaries.append(f"{label} ({count}x)" if count > 1 else label)

        is_arrow_outbound = outbound_weight >= 0
        edges.append({
            "from": entity_id if is_arrow_outbound else target_id,
            "to": target_id if is_arrow_outbound else entity_id,
            "label": "\n".join(summaries),
        })

    return {
        "nodes": list(node_info.values()),
        "edges": edges
    }
