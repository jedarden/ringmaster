# Exploration

This folder contains explorations of alternative solutions when multiple approaches exist for a problem.

## Structure

Each exploration should be a subfolder with:

```
exploration/
└── <problem-name>/
    ├── README.md           # Problem statement and comparison
    ├── option-a.md         # First approach
    ├── option-b.md         # Second approach
    └── decision.md         # Final decision and rationale (once resolved)
```

## When to Explore

Create an exploration when:
- Multiple valid architectural approaches exist
- Trade-offs are not immediately clear
- The decision has significant long-term implications
- Prototyping is needed to evaluate feasibility

## Resolution

Once an approach is chosen:
1. Create `decision.md` documenting the choice and rationale
2. Reference the decision in relevant architecture docs
3. Archive (don't delete) rejected options for future reference
