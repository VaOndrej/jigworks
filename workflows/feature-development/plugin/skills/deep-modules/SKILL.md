---
name: deep-modules
description: Use when deciding where new code goes and what its interface looks like, while planning or implementing. Deep modules behind small interfaces, seams only where something varies, and interfaces that are easy to test.
---

# Deep modules

Code that a reviewer, a test and the next agent can understand quickly has a lot of behaviour
behind a small interface. Aim for that whenever you add or reshape code.

## Vocabulary

- **Module**: anything with an interface and an implementation (a function, a class, a package).
- **Interface**: everything a caller must know to use it correctly: the signature, but also
  invariants, ordering, error modes, required configuration.
- **Deep**: much behaviour behind a small interface. **Shallow**: the interface is nearly as
  complex as what it hides (a pass-through, a wrapper that renames arguments).
- **Seam**: the place where a module's interface lives and where behaviour can be swapped
  without editing the callers. **Adapter**: a concrete thing that fills a seam.

## Rules of thumb

- **Deletion test.** Imagine deleting the module. If the complexity vanishes, it was a
  pass-through: inline it. If it reappears in every caller, it earns its place.
- **The interface is the test surface.** Tests and callers cross the same seam. If a test has to
  reach past the interface to check something, the module has the wrong shape.
- **One adapter is a hypothetical seam; two adapters make a real one.** Do not add an interface,
  a plugin point or a config option for a variation nobody has asked for. Speculative generality
  is scope creep.
- **Accept dependencies, do not create them.** Pass the clock, the gateway, the store in, so a
  test can hand in a fake at the process boundary.
- **Return results, do not mutate in place,** where the repo's style allows it. A function that
  returns a value is checkable; one that edits shared state is not.
- **Fewer methods, simpler parameters.** Every extra method or flag is more to test and more to
  get wrong. If several values always travel together, give them a type.

## In this workflow

- **Planning:** name the module that owns each new behaviour and its interface (one line). Put
  new behaviour into an existing deep module before creating a new shallow one.
- **Implementing:** follow the existing structure of the repo; do not refactor unrelated code.
  Keep internal helpers private so the tests written for the change stay valid through the
  interface the plan names.
- When the existing code has no seam where the change needs one (the logic is fused with I/O,
  for example), say so in your reply instead of adding a hack around it.
