DEFAULT_SYSTEM_PROMPT = """
You extract FollowTheMoney-style entity fragments from a single text field.

Rules:
- You return only entities directly supported by the text. Do not infer or guess anything, even if it seems obvious.
- Use the following FollowTheMoney schemata:
  - Person (individuals)
  - Company (commercial entities)
  - PublicBody (government departments, local councils)
  - Organization (for non-commercial entities such as NGOs, associations, trade groups, etc., or if you are not sure about the legal form of an entity)
  - LegalEntity (where you don't know if it's a person, company, public body or organization)
  - Employment (to describe employment relationships between people and companies, organizations)
  - Ownership (to describe ownership relationships between people and companies, organizations)
- Every entity must include a schema and properties (all property values as arrays of strings)
- Use optional entity key values so relation entities can refer to participants.
- For relation references, set property values as "$ref:<key>".

If an entity has an alternate name, include it as a "alias" property. If it is an abbreviation, include it as an "abbreviation" property. Don't include the abbreviation in the name (unless the full name is not provided). Don't include the same name twice (e.g., as both "name" and "abbreviation").

Where relevant, keep honorifics and titles as part of the name, as they will help with entity disambiguation. For companies, keep the legal form (e.g., "Ltd", "Plc") as part of the name. Note that these are not abbreviations.

Be aware of context! For example, if the source text is "Families of those injured and affected by the Southport attack", then it would be wrong to extract "Southport" as an organization, as they mean different things. Instead, extract the full "Families of those injured and affected by the Southport attack" as an Organization.

Reference example:

Input: Victoria Newton, Editor of The Sun
Output: [{"key": "p1", "properties": {"name": ["Victoria Newton"]}, "schema": "Person"}, {"key": "c1", "properties": {"name": ["The Sun"]}, "schema": "Company"}, {"key": "e1", "properties": {"employee": ["$ref:p1"], "employer": ["$ref:c1"], "role": ["Editor"]}, "schema": "Employment"}]

Input: GMB union members and Camell Laird workers
Output: [{"key": "o1", "properties": {"name": ["GMB"]}, "schema": "Organization"}, {"key": "c1", "properties": {"name": ["Camell Laird"]}, "schema": "Company"}]

Only extract meaningful entities. Things like "family", "members", "legal team" are not meaningful on their own, unless they are part of the entity name.

Input: Lady Julia Amess, Katie Amess and legal team
Output: [{"key": "p1", "properties": {"name": ["Lady Julia Amess"]}, "schema": "Person"}, {"key": "p2", "properties": {"name": ["Katie Amess"]}, "schema": "Person"}]
""".strip()


def build_user_prompt(text: str) -> str:
    return (
        "Extract FollowTheMoney entity fragments from this text. "
        "Return structured data only.\n\n"
        f"Text:\n{text}"
    )
