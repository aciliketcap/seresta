I wanted to have everything defined with generics and covariant types. But:
- JobExtractor[RawJobPosting_T_co, Repo[RawJobPosting_T_co]] can't be defined in Python. You can get close to it with Protocol's and stuff but it's too much boilerplate which convolutes the repo base class but does not present a clean solution in the end.
- I could use good ol' AbstractFactory pattern but that's again so much boilerplate and it's the exact thing Python developers want to avoid leaking in from statically typed OOP languages like Java or C#.

So I went with:
- Inheritance for extracted job data for various job source web sites. Especially since I use linked tables for inheritance in ORM side.
- Composition for repo pattern used by job extractor classes. They don't care whether the RawJobPosting objects they produce are the same type as the underlying Repo's RawJobPosting type. We just cross our fingers and rely on Python's dynamic typing (aka. duck typing).

Another, maybe better, alternative would be Ruby style mixins.

**TODO: Provide the UML diagram


