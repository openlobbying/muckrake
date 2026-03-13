---
agent: Data Analyst
---

# FollowTheMoney

[FollowTheMoney](https://followthemoney.tech/) (FtM) is a data model for financial crime investigations and document forensics.

Mappings are a mechanism for generating entities from structured data sources, including tabular data and SQL databases. Mappings are defined in YAML files that describe how information from a table can be projected to FollowTheMoney entities.

These are some (but not all) of the schemata:
- Name
- Address
- Analyzable
- Asset
- Associate
- Company
- Directorship
- Employment
- Event
- Family
- Identification
- Interest
- Interval
- LegalEntity
- License
- Membership
- Mention
- Occupancy
- Organization
- UnknownLink
- Ownership
- Payment
- Person
- Position
- Project
- ProjectParticipant
- PublicBody
- Representation
- Similar
- Succession
- Thing

Each schema has a set of properties, which can be found [here](https://followthemoney.tech/explorer/schemata/).

## Python API

For an illustration of how the schema and entity classes interact, imagine the following script.

```py
# Load the standard instance of the model
from followthemoney import model

## Schema metadata
# Access a schema metadata object
schema = model.get('Person')

# Access a property metadata object
prop = schema.get('birthDate')

## Working with entities and entity proxies
# Next, let's instantiate a proxy object for a new Person entity:
entity = model.make_entity(schema)

# First, you'll want to assign an ID to the entity. You can do this directly:
entity.id = 'john-smith'

# Or you can use a hashing function to make a safe ID:
entity.make_id('John Smith', '1979')

# Now, let's assign this entity a birthDate property (see above):
entity.add(prop, '1979-08-23')

# You can also assign properties by name:
entity.add('firstName', 'John')
entity.add('lastName', 'Smith')
entity.add('name', 'John Smith')

# Adding a property value will perform some data normalisation and validation:
entity.add('nationality', 'Atlantis')
assert not entity.has('nationality')
entity.add('nationality', 'Germani', fuzzy=True)
assert 'de' == entity.first('nationality')
enttiy.add('nationality', '阿拉伯聯合大公國')
assert 'ae' in entity.get('nationality')

# Lets make a second entity, this time for a passport:
passport_entity = model.make_entity('Passport')
passport_entity.make_id(entity.id, 'C716818')
passport_entity.add('number', 'C716818')

# Entities can link to other entities like this:
passport_entity.add('holder', entity)
# Which is the same as:
passport_entity.add('holder', entity.id)

# Finally, you can turn the contents of the entity proxy into a plain dictionary
# that is suitable for JSON serialization or storage in a database:
data = entity.to_dict()
assert data.get('id') == entity.id

# If you want to turn this back into an entity proxy:
entity2 = model.get_proxy(data)
assert entity2 == entity
```

Besides the contstruction of entities, you can also use the underlying type system used to validate property values (in this case date) directly:

```py
# You can also import the type registry that lets you access type info easily:
from followthemoney import registry
assert prop.type == registry.date

assert not registry.date.validate('BANANA')
assert registry.date.validate('2025')
```

### followthemoney.model.Model

A collection of all the schemata available in followthemoney. The model provides some helper functions to find schemata, properties or to instantiate entity proxies based on the schema metadata.

`__getitem__(name)`
Same as get(), but throws an exception when the given name does not exist.

`__iter__()`
Iterate across all schemata.

`common_schema(left, right)` cached
Select the most narrow of two schemata. When indexing data from a dataset, an entity may be declared as a LegalEntity in one query, and as a Person in another. This function will select the most specific of two schemata offered. In the example, that would be Person.

`generate()`
Loading the model is a weird process because the schemata reference each other in complex ways, so the generation process cannot be fully run as schemata are being instantiated. Hence this process needs to be called once all schemata are loaded to finalise dereferencing the schemata.

`get(name)`
Get a schema object based on a schema name. If the input is already a schema object, it will just be returned.

`get_proxy(data, cleaned=True)`
Create an entity proxy to reflect the entity data in the given dictionary. If cleaned is disabled, all property values are fully re-validated and normalised. Use this if handling input data from an untrusted source.

`get_qname(qname)`
Get a property object based on a qualified name (i.e. schema:property).

`get_type_schemata(type_)`
Return all the schemata which have a property of the given type.

`make_entity(schema, key_prefix=None)`
Instantiate an empty entity proxy of the given schema type.

`make_mapping(mapping, key_prefix=None)`
Parse a mapping that applies (tabular) source data to the model.

`map_entities(mapping, key_prefix=None)`
Given a mapping, yield a series of entities from the data source.

`matchable_schemata()`
Return a list of all schemata that are matchable.

`to_dict()`
Return metadata for all schemata and properties, in a serializable form.

### followthemoney.schema.Schema

A type definition for a class of entities that have certain properties. Schemata are arranged in a multi-rooted hierarchy: each schema can have multiple parent schemata from which it inherits all of their properties. A schema can also have descendant child schemata, which, in turn, add further properties. Schemata are usually accessed via the model, which holds all available definitions.

`__eq__(other)`
Compare two schemata (via hash).

`can_match(other)` cached
Check if an schema can match with another schema.

`description()`
A longer description of the semantics of the schema.

`edge_label()`
Description label for edges derived from entities of this schema.

`generate(model)`
While loading the schema, this function will validate and load the hierarchy, properties, and flags of the definition.

`get(name)`
Retrieve a property defined for this schema by its name.

`is_a(other)` cached
Check if the schema or one of its parents is the same as the given candidate other.

`label()`
User-facing name of the schema.

`matchable_schemata()`
Return the set of schemata to which it makes sense to compare with this schema. For example, it makes sense to compare a legal entity with a company, but it does not make sense to compare a car and a person.

`plural()`
Name of the schema to be used in plural constructions.

`sorted_properties()`
All properties of the schema in the order in which they should be shown to the user (alphabetically, with captions and featured properties first).

`source_prop()`
The entity property to be used as an edge source when the schema is considered as a relationship.

`target_prop()`
The entity property to be used as an edge target when the schema is transformed into a relationship.

`temporal_end()`
The entity properties to be used as the end when representing the entity in a timeline.

`temporal_end_props()`
The entity properties to be used as the end when representing the entity in a timeline.

`temporal_start()`
The entity properties to be used as the start when representing the entity in a timeline.

`temporal_start_props()`
The entity properties to be used as the start when representing the entity in a timeline.

`validate(data)`
Validate a dictionary against the given schema. This will also drop keys which are not valid as properties.

### Entity objects

Multiple entity object classes are available. Besides the ones documented here, a StatementEntity is implemented to support statement-based data processing.

`followthemoney.entity.ValueEntity`
Bases: EntityProxy
This class has the extended attributes from StatementEntity but without statements. Useful for streaming around. Starting from followthemoeny 4.0, applications should use this entity class as the base class.

`followthemoney.proxy.EntityProxy`
Bases: object
A wrapper object for an entity, with utility functions for the introspection and manipulation of its properties.
This is the main working object in the library, used to generate, validate and emit data.

`add(prop, values, cleaned=False, quiet=False, fuzzy=False, format=None)`
Add the given value(s) to the property if they are valid for the type of the property.
:param prop: can be given as a name or an instance of :class:~followthemoney.property.Property. :param values: either a single value, or a list of values to be added. :param cleaned: should the data be normalised before adding it. :param quiet: a reference to an non-existent property will return an empty list instead of raising an error. :param fuzzy: when normalising the data, should fuzzy matching be allowed. :param format: when normalising the data, formatting for a date.
caption()
The user-facing label to be used for this entity. This checks a list of properties defined by the schema (caption) and returns the first available value. If no caption is available, return the schema label.

`checksum()`
A SHA1 checksum hexdigest representing the current state of the entity proxy. This can be used for change detection.

`clone()`
Make a deep copy of the current entity proxy.

`countries()`
Get the set of all country-type values set of the entity.

`country_hints()`
Some property types, such as phone numbers and IBAN codes imply a country that may be associated with the entity. This list can be used for a more generous matching approach than the actual country values.

`edgepairs()`
Return all the possible pairs of values for the edge source and target if the schema allows for an edge representation of the entity.

`first(prop, quiet=False)`
Get only the first value set for the property.
:param prop: can be given as a name or an instance of :class:~followthemoney.property.Property. :param quiet: a reference to an non-existent property will return an empty list instead of raising an error. :return: A value, or None.

`from_dict(data, cleaned=True)` classmethod
Instantiate a proxy based on the given model and serialised dictionary.
Use :meth:followthemoney.model.Model.get_proxy instead.

`get(prop, quiet=False)`
Get all values of a property.
:param prop: can be given as a name or an instance of :class:~followthemoney.property.Property. :param quiet: a reference to an non-existent property will return an empty list instead of raising an error. :return: A list of values.

`get_type_inverted(matchable=False)`
Return all the values of the entity arranged into a mapping with the group name of their property type. These groups include countries, addresses, emails, etc.

`get_type_values(type_, matchable=False)`
All values of a particular type associated with a the entity. For example, this lets you return all countries linked to an entity, rather than manually checking each property to see if it contains countries.
:param type_: The type object to be searched. :param matchable: Whether to return only property values marked as matchable.

`has(prop, quiet=False)`
Check to see if the given property has at least one value set.
:param prop: can be given as a name or an instance of :class:~followthemoney.property.Property. :param quiet: a reference to an non-existent property will return an empty list instead of raising an error. :return: a boolean.

`iterprops()`
Iterate across all the properties for which a value is set in the proxy (but do not return their values).

`itervalues()`
Iterate across all values in the proxy one by one, each given as a tuple of the property and the value.

`make_id(*parts)`
Generate a (hopefully unique) ID for the given entity, composed of the given components, and the :attr:~key_prefix defined in the proxy.

`merge(other)`
Merge another entity proxy into this one. This will try and find the common schema between both entities and then add all property values from the other entity into this one.

`names()`
Get the set of all name-type values set of the entity.

`pop(prop, quiet=True)`
Remove all the values from the given property and return them.
:param prop: can be given as a name or an instance of :class:~followthemoney.property.Property. :param quiet: a reference to an non-existent property will return an empty list instead of raising an error. :return: a list of values, possibly empty.

`properties()`
Return a mapping of the properties and set values of the entity.

`remove(prop, value, quiet=True)`
Remove a single value from the given property. If it is not there, no action takes place.
:param prop: can be given as a name or an instance of :class:~followthemoney.property.Property. :param value: will not be cleaned before checking. :param quiet: a reference to an non-existent property will return an empty list instead of raising an error.

`set(prop, values, cleaned=False, quiet=False, fuzzy=False, format=None)`
Replace the values of the property with the given value(s).
:param prop: can be given as a name or an instance of :class:~followthemoney.property.Property. :param values: either a single value, or a list of values to be added. :param cleaned: should the data be normalised before adding it. :param quiet: a reference to an non-existent property will return an empty list instead of raising an error.

`temporal_end()`
Get a date that can be used to represent the end of the entity in a timeline. If therer are multiple possible dates, the latest date is returned.

`temporal_start()`
Get a date that can be used to represent the start of the entity in a timeline. If there are multiple possible dates, the earliest date is returned.

`to_dict()`
Serialise the proxy into a dictionary with the defined properties, ID, schema and any contextual values that were handed in initially. The resulting dictionary can be used to make a new proxy, and it is commonly written to disk or a database.

`to_full_dict(matchable=False)`
Return a serialised version of the entity with inverted type groups mixed in. See :meth:~get_type_inverted.

`unsafe_add(prop, value, cleaned=False, fuzzy=False, format=None)`
A version of add() to be used only in type-checking code. This accepts only a single value, and performs input cleaning on the premise that the value is already valid unicode. Returns the value that has been added.


### Property and PropertyType

`followthemoney.property.Property`
A definition of a value-holding field on a schema. Properties define the field type and other possible constraints. They also serve as entity to entity references.

`description` property
A longer description of the semantics of this property.

`label` property
User-facing title for this property.

`caption(value)`
Return a user-friendly caption for the given value.

`generate(model)`
Setup method used when loading the model in order to build out the reverse links of the property.

`specificity(value)`
Return a measure of how precise the given value is.

`to_dict()`
Return property metadata in a serializable form.

`validate(data)`
Validate that the data should be stored.
Since the types system doesn't really have validation, this currently tries to normalize the value to see if it passes strict parsing.

`followthemoney.types.common.PropertyType`
Bases: object
Base class for all property types.

`group = None` class-attribute instance-attribute
Groups are used to invert all the properties of an entity that have a given type into a single list before indexing them. This way, in Aleph, you can query for countries:gb instead of having to make a set of filters like properties.jurisdiction:gb OR properties.country:gb OR ....

`label = 'Any'` class-attribute instance-attribute
A name for this type to be shown to users.

`matchable = True` class-attribute instance-attribute
Matchable types allow properties to be compared with each other in order to assess entity similarity. While it makes sense to compare names, countries or phone numbers, the same isn't true for raw JSON blobs or descriptive text snippets.

`max_length = 250` class-attribute instance-attribute
The maximum length of a single value of this type. This is used to warn when adding individual values that may be malformed or too long to be stored in downstream databases with fixed column lengths. The unit is unicode codepoints (not bytes), the output of Python len().

`name = const('any')` class-attribute instance-attribute
A machine-facing, variable safe name for the given type.

`pivot = False` class-attribute instance-attribute
Pivot property types are like a stronger form of :attr:~matchable types: they will be used when value-based lookups are used to find commonalities between entities. For example, pivot typed-properties are used to show all the other entities that mention the same phone number, email address or name as the one currently seen by the user.

`plural = 'Any'` class-attribute instance-attribute
A plural name for this type which can be used in appropriate places in a user interface.

`total_size = None` class-attribute instance-attribute
Some types have overall size limitations in place in order to avoid generating entities that are very large (upstream ElasticSearch has a 100MB document limit). Once the total size of all properties of this type has exceed the given limit, an entity will refuse to add further values.

`caption(value, format=None)`
Return a label for the given property value. This is often the same as the value, but for types like countries or languages, it would return the label, while other values like phone numbers can be formatted to be nicer to read.

`clean(raw, fuzzy=False, format=None, proxy=None)`
Create a clean version of a value of the type, suitable for storage in an entity proxy.

`clean_text(text, fuzzy=False, format=None, proxy=None)`
Specific types can apply their own cleaning routines here (this is called by clean after the value has been converted to a string and null values have been filtered).

`compare(left, right)`
Comparisons are a float between 0 and 1. They can assume that the given data is cleaned, but not normalised.

`compare_safe(left, right)`
Compare, but support None values on either side of the comparison.

`compare_sets(left, right, func=max)`
Compare two sets of values and select the highest-scored result.

`country_hint(value)`
Determine if the given value allows us to infer a country that it may be related to (e.g. using a country prefix on a phone number or IBAN).

`join(values)`
Helper function for converting multi-valued FtM data into formats that allow only a single value per field (e.g. CSV). This is not fully reversible and should be used as a last option.

`node_id(value)`
Return an ID suitable to identify this entity as a typed node in a graph representation of some FtM data. It's usually the same as the the RDF form.

`node_id_safe(value)`
Wrapper for node_id to handle None values.

`pick(values)`
Pick the best value to show to the user.

`specificity(value)`
Return a score for how specific the given value is. This can be used as a weighting factor in entity comparisons in order to rate matching property values by how specific they are. For example: a longer address is considered to be more specific than a short one, a full date more specific than just a year number, etc.

`to_dict()`
Return a serialisable description of this data type.

`validate(value, fuzzy=False, format=None)`
Returns a boolean to indicate if the given value is a valid instance of the type.

### Statement data model

`followthemoney.statement.statement.Statement`
Bases: object
A single statement about a property relevant to an entity.
For example, this could be used to say: "In dataset A, entity X has the property name set to 'John Smith'. I first observed this at K, and last saw it at L."
Null property values are not supported. This might need to change if we want to support making property-less entities.

`clone()`
Make a deep copy of the given statement.

`make_key(dataset, entity_id, prop, value, external)` classmethod
Hash the key properties of a statement record to make a unique ID.

`prop_type()`
The type of the property, e.g. 'string', 'number', 'url'.

`followthemoney.statement.entity.StatementEntity`
Bases: EntityProxy
An entity object that can link to a set of datasets that it is sourced from.

`dataset = dataset` instance-attribute
The default dataset for new statements.

`extra_referents = set(data.pop('referents', []))` instance-attribute
The IDs of all entities which are included in this canonical entity.

`last_change = data.get('last_change', None)` instance-attribute
The last time this entity was changed.

`caption()`
The user-facing label to be used for this entity. This checks a list of properties defined by the schema (caption) and returns the first available value. If no caption is available, return the schema label.
This implementation prefers statements where the language property is that of the preferred system language.

`statements()`
Return all statements for this entity, with extra ID statement.

`to_context_dict()`
Return a dictionary representation of the entity for context.

`to_statement_dict()`
Return a dictionary representation of the entity's statements.

`unsafe_add(prop, value, cleaned=False, fuzzy=False, format=None, quiet=False, schema=None, dataset=None, seen=None, lang=None, original_value=None, origin=None)`
Add a statement to the entity, possibly the value.


### followthemoney.types.Registry

Bases: object

This registry keeps the processing helpers for all property types in the system. The registry can be used to get a type, which can itself then clean, validate or format values of that type.

`get(name)`
For a given property type name, get its type object. This can also be used via getattr, e.g. registry.phone.

`get_types(names)`
Get a list of all property type objects linked to a set of names.

# nomenklatura

Nomenklatura de-duplicates and integrates different [Follow the Money](https://followthemoney.tech/) entities. It serves to clean up messy data and to find links between different datasets.

The package offers a Python API which can be used to control the semantics of de-duplication.

* `nomenklatura.Dataset` - implements a basic dataset for describing a set of entities.
* `nomenklatura.Store` - a general purpose access mechanism for entities. By default, a store is used to access entity data stored in files as an in-memory cache, but the store can be subclassed to work with entities from a database system.
* `nomenklatura.blocker.Index` - a cross-reference blocker for correlating entities inside of a dataset, or across different datasets.
* `nomenklatura.Resolver` - the core of the de-duplication process, the resolver is essentially a graph with edges made out of entity judgements. The resolver can be used to store judgements or get the canonical ID for a given entity.

All of the API classes have extensive type annotations, which should make their integration in any modern Python API simpler.

This package offers an implementation of a data deduplication framework centered around the FtM data model. The idea is the following workflow:

* Accept FtM-shaped entities from a given source (e.g. a JSON file, or a database)
* Build an inverted index of the entities for dedupe blocking
* Generate merge candidates using the blocking index and FtM compare
* Provide a SQL persistence abstraction for merge challenges and decisions
* Provide a text-based user interface to let users make merge decisions
* Export consolidated entities that cluster source entity data