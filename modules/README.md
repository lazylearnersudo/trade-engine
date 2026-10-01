# Modules

Business capabilities live under this directory.

## Module convention

Create only the pieces a module actually needs:

```text
modules/<module>/
├── README.md
├── quickstart.md
├── CODE.md
├── ui/          # optional
├── service/     # optional
└── tests/
```

A module README defines purpose and boundaries. `CODE.md` is a concise implementation map: entry points, important files, data flow, public interfaces, invariants, common modification points, testing strategy, and known limitations.

Do not create placeholder modules before their requirements are defined.
