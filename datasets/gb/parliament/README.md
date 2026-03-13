All parliament APIs are described here: https://developer.parliament.uk/

We are interested in the following endpoints:

- Members: https://members-api.parliament.uk/
- Interests: https://interests-api.parliament.uk/
- Committees: https://committees-api.parliament.uk/
 - Committe evidence

### MPs and Lords

Each member of the UK parliament has a unique ID. Keir Starmer, for example, has the ID [`4514`](https://members.parliament.uk/member/4514/).

When creating entities for MPs and Lords, we will use these official IDs, with the prefix `GB-MEMBER-`. Thus, Keir Starmer's entity ID would be `GB-MEMBER-4514`.
